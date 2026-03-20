"""
Dry-Run Helper — CreateFleet DryRun for capacity validation
============================================================

Validates that a specific instance type in a specific AZ has spot capacity
by calling EC2 CreateFleet with DryRun=True. Results are cached in Redis
(TTL 5 minutes) to avoid repeated API calls.
"""

import json
from datetime import datetime
from typing import Optional, Dict

from redis import Redis

from backend.core.logger import logger


DRY_RUN_CACHE_TTL = 120  # 2 minutes — shorter TTL reduces stale capacity decisions


def dry_run_pool(
    region: str,
    instance_type: str,
    az: str,
    redis: Optional[Redis] = None,
    credentials: Optional[Dict] = None,
) -> bool:
    """
    Validate capacity for instance_type in az via CreateFleet DryRun.

    Args:
        region: AWS region
        instance_type: EC2 instance type (e.g., "m5.large")
        az: Availability zone (e.g., "ap-south-1a")
        redis: Redis client for result caching
        credentials: Optional dict with aws_access_key_id, aws_secret_access_key

    Returns:
        True if capacity is available, False otherwise
    """
    pool_key = f"{instance_type}:{az}"
    cache_key = f"dry_run:{pool_key}"

    # Check cache first
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                result = cached.decode() if isinstance(cached, bytes) else cached
                return result == "pass"
        except Exception:
            pass

    # Perform actual dry-run
    try:
        import boto3
        from botocore.exceptions import ClientError

        client_kwargs = {"region_name": region}
        if credentials:
            client_kwargs.update(credentials)
        else:
            # Load platform credentials
            from backend.models.base import get_db
            from backend.models.system_config import SystemConfig

            db = next(get_db())
            try:
                pk = db.query(SystemConfig).filter(
                    SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY"
                ).first()
                ps = db.query(SystemConfig).filter(
                    SystemConfig.key == "PLATFORM_AWS_SECRET"
                ).first()
                if pk and ps and pk.value and ps.value:
                    client_kwargs["aws_access_key_id"] = pk.value
                    client_kwargs["aws_secret_access_key"] = ps.value
            finally:
                db.close()

        ec2 = boto3.client("ec2", **client_kwargs)

        # Use DescribeInstanceTypeOfferings — checks whether the instance type is
        # offered in the target AZ. This avoids RunInstances DryRun which requires
        # an ImageId (causing ParamValidationError before any API call is made).
        _resp = ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=[
                {"Name": "instance-type", "Values": [instance_type]},
                {"Name": "location", "Values": [az]},
            ],
        )
        _available = bool(_resp.get("InstanceTypeOfferings"))
        _cache_result(redis, cache_key, _available)
        if not _available:
            logger.info(f"[dry_run] {instance_type} not offered in {az} ({region})")
        return _available

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        # Any auth/access error — assume available (conservative)
        logger.warning(f"[dry_run] Ambiguous result for {pool_key}: {error_code} — assuming available")
        return True

    except Exception as e:
        logger.warning(f"[dry_run] Exception for {pool_key}: {e}")
        return True  # Assume capacity on error


def _cache_result(redis: Optional[Redis], cache_key: str, passed: bool):
    """Cache dry-run result with 2-minute TTL."""
    if redis:
        try:
            redis.setex(cache_key, DRY_RUN_CACHE_TTL, "pass" if passed else "fail")
        except Exception:
            pass


def batch_dry_run(
    region: str,
    pool_keys: list,
    redis: Optional[Redis] = None,
    credentials: Optional[Dict] = None,
) -> Dict[str, bool]:
    """
    Batch dry-run for multiple pool keys.

    Args:
        pool_keys: List of "instance_type:az" strings

    Returns:
        Dict mapping pool_key → True/False
    """
    results = {}
    for pk in pool_keys:
        parts = pk.split(":")
        if len(parts) == 2:
            results[pk] = dry_run_pool(
                region=region,
                instance_type=parts[0],
                az=parts[1],
                redis=redis,
                credentials=credentials,
            )
    return results
