"""
Regional AWS Pricing Worker (Enterprise Remediation Phase 1)
==============================================================

Celery tasks for enterprise-grade pricing management with freshness guarantees.

Task Schedule:
- Regional pricing refresh: Every 10 minutes (per region)
- Freshness validation: Before each optimization execution
- Stale pricing alerts: Debounced (1 hour)

Enterprise Guardrails:
- 15-minute freshness threshold (blocks new optimizations if stale)
- Regional aggregation (minimizes AWS API calls)
- Adaptive retry (max_attempts=10, mode=adaptive)
- In-flight executions continue (never force On-Demand mid-drain)
"""
import logging
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session

from backend.workers.app import app
from backend.models.base import SessionLocal
from backend.models.cluster import Cluster
from backend.services.aws_pricing_service import AWSPricingService, PricingFreshnessException
from backend.core.redis_client import get_redis_client
import json

logger = logging.getLogger(__name__)


@app.task(name='workers.pricing.refresh_regional_pricing')
def refresh_regional_pricing(region: str = None):
    """
    Refresh AWS pricing for a specific region or all regions.

    This task runs every 10 minutes and:
    1. Aggregates required instance types across all clusters in region
    2. Batch fetches spot prices via EC2 API
    3. Batch fetches on-demand prices via Pricing API
    4. Caches results in Redis with 10-minute TTL
    5. Updates last_updated timestamp

    Args:
        region: AWS region (e.g., 'us-east-1'). If None, refresh all regions.

    Enterprise Guardrail:
        Updates pricing:last_updated:{region} timestamp.
        If not updated within 15 minutes, optimizations will be blocked.
    """
    db = SessionLocal()
    redis = get_redis_client()

    try:
        pricing_service = AWSPricingService(db, redis)

        # Get all active regions from clusters
        if region:
            regions_to_refresh = [region]
        else:
            regions_to_refresh = get_active_regions(db)

        logger.info(f"Starting regional pricing refresh for {len(regions_to_refresh)} regions")

        results = {}
        for reg in regions_to_refresh:
            try:
                logger.info(f"Refreshing pricing for region: {reg}")

                # Refresh regional pricing (spot + on-demand)
                stats = pricing_service.refresh_regional_pricing_batch(
                    region=reg,
                    instance_types=None  # Auto-detect from clusters
                )

                results[reg] = {
                    "status": "success",
                    "spot_prices_fetched": stats["spot_prices_fetched"],
                    "ondemand_prices_fetched": stats["ondemand_prices_fetched"],
                    "timestamp": datetime.utcnow().isoformat()
                }

                logger.info(
                    f"Successfully refreshed pricing for {reg}: "
                    f"{stats['spot_prices_fetched']} spot, "
                    f"{stats['ondemand_prices_fetched']} on-demand"
                )

            except Exception as e:
                logger.error(f"Failed to refresh pricing for {reg}: {e}", exc_info=True)
                results[reg] = {
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }

        # Store global summary in Redis
        summary = {
            "last_refresh": datetime.utcnow().isoformat(),
            "regions_processed": len(regions_to_refresh),
            "results": results
        }

        redis.setex(
            "pricing:global_refresh_summary",
            3600,  # 1 hour TTL
            json.dumps(summary)
        )

        logger.info(f"Regional pricing refresh complete: {len(results)} regions")

        return results

    except Exception as e:
        logger.error(f"Regional pricing refresh failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


@app.task(name='workers.pricing.validate_pricing_freshness')
def validate_pricing_freshness(region: str):
    """
    Validate that pricing for a region is fresh (< 15 minutes old).

    This task is called BEFORE executing any optimization to enforce
    the enterprise freshness contract.

    Args:
        region: AWS region to validate

    Returns:
        Dict with freshness status

    Raises:
        PricingFreshnessException: If pricing is stale

    Enterprise Guardrail:
        - Blocks new optimizations if pricing is stale (> 15 min)
        - Marks clusters as PRICING_STALE
        - Emits regional alert (debounced)
        - In-flight executions continue
    """
    db = SessionLocal()
    redis = get_redis_client()

    try:
        pricing_service = AWSPricingService(db, redis)

        # This will raise PricingFreshnessException if stale
        pricing_service._enforce_pricing_freshness(region)

        is_fresh, age_minutes = pricing_service.is_pricing_fresh(region)

        logger.info(f"Pricing freshness check passed for {region}: {age_minutes:.1f} minutes old")

        return {
            "region": region,
            "is_fresh": is_fresh,
            "age_minutes": age_minutes,
            "status": "fresh"
        }

    except PricingFreshnessException as e:
        logger.warning(f"Pricing freshness check failed for {region}: {e}")
        raise

    finally:
        db.close()


@app.task(name='workers.pricing.emergency_pricing_refresh')
def emergency_pricing_refresh(region: str):
    """
    Emergency pricing refresh triggered when stale pricing is detected.

    This task:
    1. Immediately fetches fresh pricing for the region
    2. Clears PRICING_STALE flags on clusters
    3. Emits success notification

    Args:
        region: AWS region to refresh

    Returns:
        Dict with refresh status
    """
    db = SessionLocal()
    redis = get_redis_client()

    try:
        logger.warning(f"EMERGENCY PRICING REFRESH triggered for {region}")

        pricing_service = AWSPricingService(db, redis)

        # Force refresh
        stats = pricing_service.refresh_regional_pricing_batch(
            region=region,
            instance_types=None
        )

        # Clear PRICING_STALE flags
        clusters = db.query(Cluster).filter(Cluster.region == region).all()
        for cluster in clusters:
            stale_key = f"cluster:{cluster.id}:pricing_stale"
            redis.delete(stale_key)

        logger.info(
            f"Emergency pricing refresh complete for {region}: "
            f"{stats['spot_prices_fetched']} spot, {stats['ondemand_prices_fetched']} on-demand"
        )

        return {
            "region": region,
            "status": "success",
            "spot_prices_fetched": stats["spot_prices_fetched"],
            "ondemand_prices_fetched": stats["ondemand_prices_fetched"],
            "clusters_cleared": len(clusters),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Emergency pricing refresh failed for {region}: {e}", exc_info=True)
        raise

    finally:
        db.close()


@app.task(name='workers.pricing.get_pricing_health')
def get_pricing_health():
    """
    Get global pricing health status across all regions.

    Returns:
        Dict with per-region freshness status
    """
    db = SessionLocal()
    redis = get_redis_client()

    try:
        pricing_service = AWSPricingService(db, redis)
        regions = get_active_regions(db)

        health_status = {}

        for region in regions:
            is_fresh, age_minutes = pricing_service.is_pricing_fresh(region)

            health_status[region] = {
                "is_fresh": is_fresh,
                "age_minutes": age_minutes,
                "threshold_minutes": pricing_service.FRESHNESS_THRESHOLD_MINUTES,
                "status": "healthy" if is_fresh else "stale"
            }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_regions": len(regions),
            "healthy_regions": sum(1 for s in health_status.values() if s["is_fresh"]),
            "stale_regions": sum(1 for s in health_status.values() if not s["is_fresh"]),
            "regions": health_status
        }

    finally:
        db.close()


def get_active_regions(db: Session) -> List[str]:
    """
    Get list of active AWS regions from clusters.

    Args:
        db: Database session

    Returns:
        List of unique regions
    """
    clusters = db.query(Cluster.region).distinct().all()
    regions = [c.region for c in clusters if c.region]

    # Default to us-east-1 if no clusters
    if not regions:
        regions = ['us-east-1']

    return regions
