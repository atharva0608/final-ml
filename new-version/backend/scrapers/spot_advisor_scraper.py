"""
Spot Advisor Scraper (SVC-SCRAPE-01)
AWS Spot Instance Advisor data collection service

Scrapes AWS Spot Instance Advisor to collect interruption frequency ratings
and savings percentages for all instance types across all regions.

Data Source: https://aws.amazon.com/ec2/spot/instance-advisor/
API Endpoint: https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json

Key Features:
- Automated daily scraping of Spot Advisor data
- Region-specific interruption frequency ratings (<5%, 5-10%, 10-15%, 15-20%, >20%)
- Savings percentage calculations vs On-Demand
- Historical data tracking
- Redis caching for fast lookups

Update Frequency: Daily at 2:00 AM UTC

Dependencies:
- requests for HTTP calls
- SQLAlchemy for data persistence
- Redis for caching
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database.session import get_db
from app.database.models import SpotAdvisorData
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# AWS Spot Advisor public API endpoint
SPOT_ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"

# Interruption frequency mappings
FREQUENCY_RATINGS = {
    0: "<5%",
    1: "5-10%",
    2: "10-15%",
    3: "15-20%",
    4: ">20%"
}


def scrape_spot_advisor_data() -> Dict[str, Any]:
    """
    Scrape AWS Spot Advisor data

    Returns:
        Dict with scraping results and statistics
    """
    logger.info("[SVC-SCRAPE-01] Starting Spot Advisor data scrape")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        # Fetch data from AWS S3
        response = requests.get(SPOT_ADVISOR_URL, timeout=30)
        response.raise_for_status()

        data = response.json()

        logger.info(f"[SVC-SCRAPE-01] Fetched Spot Advisor data successfully")

        # Parse and store data
        stats = parse_and_store_data(data, db, redis_client)

        logger.info(f"[SVC-SCRAPE-01] Scrape complete: {stats}")

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "stats": stats
        }

    except requests.RequestException as e:
        logger.error(f"[SVC-SCRAPE-01] HTTP error: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

    except Exception as e:
        logger.error(f"[SVC-SCRAPE-01] Unexpected error: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

    finally:
        db.close()


def parse_and_store_data(
    data: Dict[str, Any],
    db: Session,
    redis_client
) -> Dict[str, int]:
    """
    Parse Spot Advisor JSON and store in database + Redis

    Args:
        data: Raw JSON data from Spot Advisor API
        db: Database session
        redis_client: Redis client

    Returns:
        Dict with parsing statistics
    """
    stats = {
        "instance_types_processed": 0,
        "regions_processed": 0,
        "records_created": 0,
        "records_updated": 0,
        "cache_keys_set": 0
    }

    # Extract instance type data
    # Data structure: {"spot_advisor": {"Linux": {...}}}
    spot_data = data.get("spot_advisor", {})

    for os_type, os_data in spot_data.items():
        logger.info(f"[SVC-SCRAPE-01] Processing OS type: {os_type}")

        # Iterate through regions
        for region, region_data in os_data.items():
            if region == "ranges":
                continue  # Skip the ranges metadata

            stats["regions_processed"] += 1

            # Iterate through instance types in this region
            for instance_type, instance_data in region_data.items():
                stats["instance_types_processed"] += 1

                # Parse instance data
                # Format: {"r": interruption_frequency_index, "s": savings_percentage}
                interruption_index = instance_data.get("r", 0)
                savings_percentage = instance_data.get("s", 0)

                interruption_frequency = FREQUENCY_RATINGS.get(interruption_index, "unknown")

                # Store in database
                existing = db.query(SpotAdvisorData).filter(
                    and_(
                        SpotAdvisorData.instance_type == instance_type,
                        SpotAdvisorData.region == region,
                        SpotAdvisorData.os_type == os_type
                    )
                ).first()

                if existing:
                    # Update existing record
                    existing.interruption_frequency = interruption_frequency
                    existing.interruption_index = interruption_index
                    existing.savings_percentage = savings_percentage
                    existing.updated_at = datetime.utcnow()
                    stats["records_updated"] += 1
                else:
                    # Create new record
                    advisor_data = SpotAdvisorData(
                        instance_type=instance_type,
                        region=region,
                        os_type=os_type,
                        interruption_frequency=interruption_frequency,
                        interruption_index=interruption_index,
                        savings_percentage=savings_percentage
                    )
                    db.add(advisor_data)
                    stats["records_created"] += 1

                # Cache in Redis for fast lookup
                cache_key = f"spot_advisor:{region}:{instance_type}:{os_type}"
                cache_value = json.dumps({
                    "interruption_frequency": interruption_frequency,
                    "interruption_index": interruption_index,
                    "savings_percentage": savings_percentage
                })

                redis_client.setex(cache_key, 86400, cache_value)  # Cache for 24 hours
                stats["cache_keys_set"] += 1

        db.commit()

    return stats


def get_spot_advisor_rating(
    instance_type: str,
    region: str,
    os_type: str = "Linux",
    db: Optional[Session] = None,
    redis_client=None
) -> Optional[Dict[str, Any]]:
    """
    Get Spot Advisor rating for an instance type

    Checks Redis cache first, falls back to database if not cached.

    Args:
        instance_type: EC2 instance type (e.g., "m5.large")
        region: AWS region (e.g., "us-east-1")
        os_type: Operating system type (default: "Linux")
        db: Optional database session
        redis_client: Optional Redis client

    Returns:
        Dict with interruption data, or None if not found
    """
    if redis_client is None:
        redis_client = get_redis_client()

    # Try Redis cache first
    cache_key = f"spot_advisor:{region}:{instance_type}:{os_type}"
    cached_data = redis_client.get(cache_key)

    if cached_data:
        logger.debug(f"[SVC-SCRAPE-01] Cache hit for {instance_type} in {region}")
        return json.loads(cached_data)

    # Cache miss - query database
    logger.debug(f"[SVC-SCRAPE-01] Cache miss for {instance_type} in {region}, querying database")

    if db is None:
        db = next(get_db())

    try:
        advisor_data = db.query(SpotAdvisorData).filter(
            and_(
                SpotAdvisorData.instance_type == instance_type,
                SpotAdvisorData.region == region,
                SpotAdvisorData.os_type == os_type
            )
        ).first()

        if advisor_data:
            result = {
                "interruption_frequency": advisor_data.interruption_frequency,
                "interruption_index": advisor_data.interruption_index,
                "savings_percentage": advisor_data.savings_percentage
            }

            # Populate cache
            redis_client.setex(cache_key, 86400, json.dumps(result))

            return result
        else:
            logger.warning(f"[SVC-SCRAPE-01] No data found for {instance_type} in {region}")
            return None

    finally:
        if db:
            db.close()


def get_low_interruption_instances(
    region: str,
    max_interruption_index: int = 1,
    min_savings: int = 50,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Find instance types with low interruption risk and high savings

    Useful for recommending safe Spot instances to users.

    Args:
        region: AWS region
        max_interruption_index: Maximum interruption index (0=<5%, 1=5-10%, etc.)
        min_savings: Minimum savings percentage vs On-Demand
        db: Optional database session

    Returns:
        List of instance types matching criteria
    """
    logger.info(
        f"[SVC-SCRAPE-01] Finding low-interruption instances in {region} "
        f"(interruption <= {max_interruption_index}, savings >= {min_savings}%)"
    )

    if db is None:
        db = next(get_db())

    try:
        results = db.query(SpotAdvisorData).filter(
            and_(
                SpotAdvisorData.region == region,
                SpotAdvisorData.interruption_index <= max_interruption_index,
                SpotAdvisorData.savings_percentage >= min_savings
            )
        ).order_by(SpotAdvisorData.savings_percentage.desc()).all()

        instances = []
        for result in results:
            instances.append({
                "instance_type": result.instance_type,
                "interruption_frequency": result.interruption_frequency,
                "interruption_index": result.interruption_index,
                "savings_percentage": result.savings_percentage
            })

        logger.info(f"[SVC-SCRAPE-01] Found {len(instances)} matching instances")

        return instances

    finally:
        if db:
            db.close()


def calculate_risk_score(
    instance_type: str,
    region: str,
    db: Optional[Session] = None,
    redis_client=None
) -> float:
    """
    Calculate normalized risk score (0.0-1.0) for instance type

    Uses Spot Advisor interruption frequency as base score.
    Lower is better.

    Args:
        instance_type: EC2 instance type
        region: AWS region
        db: Optional database session
        redis_client: Optional Redis client

    Returns:
        Risk score (0.0 = safest, 1.0 = riskiest)
    """
    advisor_data = get_spot_advisor_rating(
        instance_type=instance_type,
        region=region,
        db=db,
        redis_client=redis_client
    )

    if not advisor_data:
        # No data available - assume moderate risk
        logger.warning(f"[SVC-SCRAPE-01] No advisor data for {instance_type}, assuming 0.5 risk")
        return 0.5

    # Convert interruption index (0-4) to risk score (0.0-1.0)
    interruption_index = advisor_data["interruption_index"]
    risk_score = interruption_index / 4.0

    return risk_score


def refresh_cache_for_region(
    region: str,
    db: Optional[Session] = None,
    redis_client=None
) -> int:
    """
    Refresh Redis cache for all instance types in a region

    Useful after database updates or cache invalidation.

    Args:
        region: AWS region
        db: Optional database session
        redis_client: Optional Redis client

    Returns:
        Number of cache keys refreshed
    """
    logger.info(f"[SVC-SCRAPE-01] Refreshing cache for region {region}")

    if db is None:
        db = next(get_db())

    if redis_client is None:
        redis_client = get_redis_client()

    try:
        # Query all instance types in this region
        instances = db.query(SpotAdvisorData).filter(
            SpotAdvisorData.region == region
        ).all()

        count = 0
        for instance in instances:
            cache_key = f"spot_advisor:{region}:{instance.instance_type}:{instance.os_type}"
            cache_value = json.dumps({
                "interruption_frequency": instance.interruption_frequency,
                "interruption_index": instance.interruption_index,
                "savings_percentage": instance.savings_percentage
            })

            redis_client.setex(cache_key, 86400, cache_value)
            count += 1

        logger.info(f"[SVC-SCRAPE-01] Refreshed {count} cache keys for {region}")

        return count

    finally:
        if db:
            db.close()


# Celery task wrapper (if using Celery)
try:
    from app.core.celery_app import app as celery_app
    from celery import Task

    @celery_app.task(bind=True, name="scrapers.spot_advisor.scrape")
    def scrape_spot_advisor_task(self: Task) -> Dict[str, Any]:
        """
        Celery task for scheduled Spot Advisor scraping

        Runs daily at 2:00 AM UTC via Celery Beat
        """
        return scrape_spot_advisor_data()

except ImportError:
    logger.warning("[SVC-SCRAPE-01] Celery not available, task scheduling disabled")
