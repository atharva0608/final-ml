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
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
import json
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.base import get_db
from backend.models.pricing import SpotAdvisorData
from backend.core.redis_client import get_redis_client
from backend.core.config import DEFAULT_INTERRUPTION_RATE_PCT, SPOT_ADVISOR_STALENESS_DAYS

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

# Bug 4: Correct r-index → interruption-rate-percentage mapping.
# AWS returns r=0 (<5%), r=1 (5-10%), ..., r=4 (>20%).
# We store the UPPER BOUND of the range in SpotAdvisorRate.interruption_rate_pct.
# Missing r → 100.0 (treat as completely unknown = maximum risk).
INDEX_TO_PCT: dict = {
    0: 5.0,
    1: 10.0,
    2: 15.0,
    3: 20.0,
    4: 25.0,
}
INDEX_TO_PCT_MISSING = 100.0  # sentinel for missing r-key


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

        # Task 1.1: Per-region hash dedup happens inside parse_and_store_data().
        # We pass the full JSON data to it and let it skip unchanged regions.
        stats = parse_and_store_data(data, db, redis_client)

        # Write global last_scraped so monitoring can check overall freshness.
        redis_client.set("spot:advisor:last_scraped", datetime.utcnow().isoformat())

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
    import hashlib as _hashlib

    stats = {
        "instance_types_processed": 0,
        "regions_processed": 0,
        "records_created": 0,
        "records_updated": 0,
        "cache_keys_set": 0,
        "regions_skipped_unchanged": 0,
    }

    # Extract instance type data
    # Data structure: {"spot_advisor": {"Linux": {...}}}
    spot_data = data.get("spot_advisor", {})

    from backend.models.spot_advisor_rates import SpotAdvisorRate
    today = datetime.utcnow().date()

    # The actual AWS Spot Advisor JSON structure is: region → os_type → instance_type
    # e.g. {"ap-south-1": {"Linux": {"t3.medium": {"r": 0, "s": 73}}}}
    for region, region_data in spot_data.items():
        if region == "ranges":
            continue  # Skip the ranges metadata

        # Task 1.1: Per-region hash dedup — skip DB writes if this region unchanged.
        # Key: spot:advisor:hash:{region}  (NOT a global blob hash)
        linux_data = region_data.get("Linux", {})
        if not isinstance(linux_data, dict):
            continue
        _region_hash = _hashlib.sha256(
            json.dumps(linux_data, sort_keys=True).encode()
        ).hexdigest()
        _old_region_hash = redis_client.get(f"spot:advisor:hash:{region}")
        if _old_region_hash:
            _old_region_hash = _old_region_hash.decode("utf-8") if isinstance(_old_region_hash, bytes) else _old_region_hash
        if _region_hash == _old_region_hash:
            # Data unchanged — skip DB writes only, but STILL refresh Redis keys
            # (Redis TTL is 12h; if we only run every 12h and skip writes, keys expire before next run)
            redis_client.set(f"spot:advisor:last_scraped:{region}", datetime.utcnow().isoformat())
            stats["regions_skipped_unchanged"] += 1
            logger.debug(f"[SVC-SCRAPE-01] Region {region} hash unchanged — refreshing Redis TTL only (skipping DB writes)")
            # Fall through to refresh Redis keys below — do NOT continue

        logger.info(f"[SVC-SCRAPE-01] Processing region: {region}")

        # Bug 2: Hardcode Linux — EKS nodes never run Windows/SUSE.
        # linux_data already computed above for hash comparison.
        os_type = "Linux"
        stats["regions_processed"] += 1

        # Iterate through instance types in this region+OS combo
        for instance_type, instance_data in linux_data.items():
            if not isinstance(instance_data, dict):
                continue
            stats["instance_types_processed"] += 1

            # Parse instance data
            # Format: {"r": interruption_frequency_index, "s": savings_percentage}
            # Bug 1: r is sometimes absent for newer instance types not yet rated.
            # Default was 0 (safest) — wrong. Unknown = treat as worst known (4 = >20%).
            raw_r = instance_data.get("r")
            if raw_r is None:
                interruption_index = 4  # Unknown → worst-case (>20%)
                logger.debug(
                    f"[SVC-SCRAPE-01] Missing 'r' for {instance_type}/{region} "
                    f"— defaulting to index 4 (>20% interruption)"
                )
            else:
                interruption_index = int(raw_r)
            savings_percentage = instance_data.get("s", 0)

            interruption_frequency = FREQUENCY_RATINGS.get(interruption_index, ">20%")

            # ── Write to SpotAdvisorData (stores raw 0-4 index for pool filter) ──
            existing = db.query(SpotAdvisorData).filter(
                and_(
                    SpotAdvisorData.instance_type == instance_type,
                    SpotAdvisorData.region == region,
                    SpotAdvisorData.os_type == os_type
                )
            ).first()

            if existing:
                existing.interruption_frequency = interruption_frequency
                existing.interruption_index = interruption_index
                existing.savings_percentage = savings_percentage
                existing.updated_at = datetime.utcnow()
                stats["records_updated"] += 1
            else:
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

            # ── Bug 4: Write to SpotAdvisorRate (stores percentage for get_interruption_rate) ──
            # INDEX_TO_PCT: r=0→5.0, r=1→10.0, r=2→15.0, r=3→20.0, r=4→25.0
            # Missing r → INDEX_TO_PCT_MISSING (100.0) — excluded from ranking as too risky
            rate_pct = INDEX_TO_PCT.get(interruption_index, INDEX_TO_PCT_MISSING) if raw_r is not None else INDEX_TO_PCT_MISSING
            rate_category = interruption_frequency
            # Use PostgreSQL ON CONFLICT DO UPDATE (atomic upsert) to handle:
            # 1. Records from a previous day (valid_from mismatch → INSERT would fail constraint)
            # 2. Concurrent scraper calls racing on the same (region, instance_type)
            # The DB unique constraint "uq_spot_advisor_region_type" is on (region, instance_type).
            upsert_stmt = pg_insert(SpotAdvisorRate.__table__).values(
                id=str(uuid4()),
                region=region,
                instance_type=instance_type,
                interruption_rate_category=rate_category,
                interruption_rate_pct=rate_pct,
                valid_from=today,
                scraped_at=datetime.utcnow(),
            ).on_conflict_do_update(
                index_elements=['region', 'instance_type'],
                set_={
                    'interruption_rate_category': rate_category,
                    'interruption_rate_pct': rate_pct,
                    'valid_from': today,
                    'scraped_at': datetime.utcnow(),
                }
            )
            db.execute(upsert_stmt)

            # Cache in Redis for fast lookup (Bug 3: TTL reduced to 12h)
            cache_key = f"spot_advisor:{region}:{instance_type}:{os_type}"
            cache_value = json.dumps({
                "interruption_frequency": interruption_frequency,
                "interruption_index": interruption_index,
                "savings_percentage": savings_percentage
            })
            redis_client.setex(cache_key, 43200, cache_value)  # Bug 3: 12h TTL (was 24h)
            stats["cache_keys_set"] += 1

        db.commit()
        # Task 1.1: write per-region hash + timestamp after successful write
        redis_client.set(f"spot:advisor:hash:{region}", _region_hash)
        redis_client.set(f"spot:advisor:last_scraped:{region}", datetime.utcnow().isoformat())

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


def get_interruption_rate(region: str, instance_type: str, db: Session) -> float:
    """
    Get interruption rate percentage for an instance type in a region.

    3-step fallback chain:
    1. Exact match (region + instance_type) in spot_advisor_rates table
    2. Family average (e.g., m5 family average for m5.large)
    3. DEFAULT_INTERRUPTION_RATE_PCT (15.0)

    Also checks staleness: if latest valid_from > SPOT_ADVISOR_STALENESS_DAYS old, logs CRITICAL.
    """
    try:
        from backend.models.spot_advisor_rates import SpotAdvisorRate
        from sqlalchemy import func

        # Step 1: Exact match
        exact = db.query(SpotAdvisorRate).filter(
            SpotAdvisorRate.region == region,
            SpotAdvisorRate.instance_type == instance_type,
        ).order_by(SpotAdvisorRate.valid_from.desc()).first()

        if exact:
            # Staleness check
            if exact.valid_from:
                age_days = (date.today() - exact.valid_from).days
                if age_days > SPOT_ADVISOR_STALENESS_DAYS:
                    logger.critical(
                        f"[spot_advisor] Data for {instance_type}/{region} is {age_days} days old "
                        f"(threshold: {SPOT_ADVISOR_STALENESS_DAYS} days)"
                    )
            return exact.interruption_rate_pct

        # Step 2: Family average (prefix before first dot, e.g. "m5" from "m5.large")
        family = instance_type.split('.')[0]
        family_rates = db.query(
            func.avg(SpotAdvisorRate.interruption_rate_pct)
        ).filter(
            SpotAdvisorRate.region == region,
            SpotAdvisorRate.instance_type.like(f'{family}.%'),
        ).scalar()

        if family_rates is not None:
            return float(family_rates)

        # Step 3: Default
        logger.warning(
            f"[spot_advisor] No data for {instance_type} in {region}, using default "
            f"{DEFAULT_INTERRUPTION_RATE_PCT}%"
        )
        return DEFAULT_INTERRUPTION_RATE_PCT

    except Exception as e:
        logger.error(f"[spot_advisor] get_interruption_rate error: {e}")
        return DEFAULT_INTERRUPTION_RATE_PCT


# Celery task wrapper (if using Celery)
try:
    from backend.core.celery_app import app as celery_app
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
