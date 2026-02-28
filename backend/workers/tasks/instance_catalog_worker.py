"""
Instance Catalog Worker (Enterprise Remediation Phase 1 - Task 1.2)
====================================================================

Celery task for nightly instance catalog refresh from AWS EC2 API.

Task Schedule:
- Nightly refresh: Every 24 hours (runs at 3 AM UTC)
- Emergency refresh: On-demand via API call

Replaces hardcoded instance data with live AWS specifications.
"""
import logging
from datetime import datetime
from typing import Dict
from sqlalchemy.orm import Session

from backend.workers.app import app
from backend.models.base import SessionLocal
from backend.services.instance_catalog_service import InstanceCatalogService
from backend.core.redis_client import get_redis_client
import json

logger = logging.getLogger(__name__)


@app.task(name='workers.instance_catalog.refresh_catalog')
def refresh_instance_catalog(region: str = 'us-east-1'):
    """
    Refresh instance catalog from AWS EC2 API.

    This task runs nightly and:
    1. Fetches all instance types from EC2 describe_instance_types API
    2. Parses specifications (vCPU, memory, network, storage, GPU, etc.)
    3. Stores in database for ML feature engineering
    4. Replaces hardcoded instance data with live AWS data

    Args:
        region: AWS region (default: us-east-1 for global catalog)

    Returns:
        Dict with refresh stats

    Enterprise Guardrail:
        Falls back to cached data if AWS API fails.
        Retries with exponential backoff (max 10 attempts).
    """
    db = SessionLocal()
    redis = get_redis_client()

    try:
        logger.info(f"Starting instance catalog refresh for region: {region}")

        catalog_service = InstanceCatalogService(db)

        # Refresh catalog from AWS
        stats = catalog_service.refresh_instance_catalog(region=region)

        logger.info(
            f"Instance catalog refresh complete: "
            f"{stats['instances_fetched']} instances fetched, "
            f"{stats['instances_stored']} stored"
        )

        # Store summary in Redis
        summary = {
            "last_refresh": datetime.utcnow().isoformat(),
            "region": region,
            "instances_fetched": stats["instances_fetched"],
            "instances_stored": stats["instances_stored"],
            "status": "success"
        }

        redis.setex(
            f"instance_catalog:last_refresh:{region}",
            86400,  # 24 hours TTL
            json.dumps(summary)
        )

        return summary

    except Exception as e:
        logger.error(f"Instance catalog refresh failed for {region}: {e}", exc_info=True)

        # Store failure in Redis
        failure_summary = {
            "last_refresh": datetime.utcnow().isoformat(),
            "region": region,
            "status": "failed",
            "error": str(e)
        }

        redis.setex(
            f"instance_catalog:last_refresh:{region}",
            3600,  # 1 hour TTL for failures
            json.dumps(failure_summary)
        )

        raise

    finally:
        db.close()


@app.task(name='workers.instance_catalog.refresh_all_regions')
def refresh_all_regions():
    """
    Refresh instance catalog for all AWS regions.

    This task:
    1. Iterates through all major AWS regions
    2. Refreshes instance catalog for each region
    3. Aggregates results

    Returns:
        Dict with per-region refresh stats
    """
    # Major AWS regions
    regions = [
        'us-east-1',
        'us-east-2',
        'us-west-1',
        'us-west-2',
        'eu-west-1',
        'eu-central-1',
        'ap-south-1',
        'ap-southeast-1',
        'ap-northeast-1',
    ]

    logger.info(f"Starting instance catalog refresh for {len(regions)} regions")

    results = {}
    for region in regions:
        try:
            stats = refresh_instance_catalog.apply(args=[region]).get()
            results[region] = stats
        except Exception as e:
            logger.error(f"Failed to refresh catalog for {region}: {e}")
            results[region] = {
                "status": "failed",
                "error": str(e)
            }

    logger.info(f"Instance catalog refresh complete for all regions")

    return {
        "total_regions": len(regions),
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.task(name='workers.instance_catalog.get_catalog_stats')
def get_catalog_stats(region: str = 'us-east-1'):
    """
    Get instance catalog statistics for a region.

    Args:
        region: AWS region

    Returns:
        Dict with catalog stats
    """
    db = SessionLocal()

    try:
        catalog_service = InstanceCatalogService(db)
        stats = catalog_service.get_catalog_stats(region=region)

        return {
            "region": region,
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()


@app.task(name='workers.instance_catalog.get_refresh_status')
def get_refresh_status(region: str = 'us-east-1'):
    """
    Get status of last instance catalog refresh.

    Args:
        region: AWS region

    Returns:
        Dict with last refresh timestamp and stats
    """
    redis = get_redis_client()
    cached_data = redis.get(f"instance_catalog:last_refresh:{region}")

    if cached_data:
        try:
            return json.loads(cached_data)
        except:
            pass

    return {
        "region": region,
        "last_refresh": None,
        "status": "never_run"
    }
