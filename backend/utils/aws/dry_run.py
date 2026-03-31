"""
Dry-Run Helper — RunInstances DryRun for real spot capacity validation
======================================================================

Validates that a specific instance type in a specific AZ has ACTUAL spot
capacity by calling EC2 RunInstances with DryRun=True.

DryRun=True with InstanceMarketOptions.MarketType=spot returns:
  - DryRunOperation  → capacity available (treat as PASS)
  - InsufficientInstanceCapacity → no capacity (treat as FAIL)
  - Other ClientError → fail-safe (treat as FAIL)

Results cached in Redis:
  pass → 600s TTL (10 min)
  fail → 60s TTL  (1 min, retry quickly — reduces cross-cluster blocking)

AMI ID is resolved once per region via describe_images and cached 24h.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

from redis import Redis

from backend.core.logger import logger


DRY_RUN_PASS_TTL = 900  # 15 minutes (Problem #4: was 480s — stale capacity could cause launch failures)
DRY_RUN_FAIL_TTL = 60  # N8 fix: 60s (was 300s) — retry failed pools faster, reduces cross-cluster blocking
DRY_RUN_CACHE_TTL = DRY_RUN_PASS_TTL  # backward-compat alias

_AMI_CACHE_TTL = 86400  # 24 hours


def _get_ami_for_region(ec2, region: str, redis: Optional[Redis], architecture: str = "amd64") -> Optional[str]:
    """
    Return a recent Amazon Linux 2 AMI ID for the given region and architecture.
    Cached in Redis for 24 hours to avoid repeated describe_images calls.

    architecture: "amd64" (x86_64) or "arm64"
    """
    cache_key = f"dry_run:ami:{region}:{architecture}"
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass

    # Build name filter based on architecture
    if architecture == "arm64":
        name_filter = 'amzn2-ami-hvm-*-arm64-gp2'
    else:
        name_filter = 'amzn2-ami-hvm-*-x86_64-gp2'

    try:
        resp = ec2.describe_images(
            Owners=['amazon'],
            Filters=[
                {'Name': 'name', 'Values': [name_filter]},
                {'Name': 'state', 'Values': ['available']},
            ],
        )
        images = sorted(resp.get('Images', []), key=lambda x: x.get('CreationDate', ''), reverse=True)
        if not images:
            return None
        ami_id = images[0]['ImageId']
        if redis:
            try:
                redis.setex(cache_key, _AMI_CACHE_TTL, ami_id)
            except Exception:
                pass
        return ami_id
    except Exception as e:
        logger.debug(f"[dry_run] describe_images failed for {region}/{architecture}: {e}")
        return None


def get_eks_ami(region: str, architecture: str = "amd64", redis: Optional[Redis] = None) -> Optional[str]:
    """
    Return the latest EKS-optimized AMI ID for the given region and architecture.
    Checks for EKS-specific AMIs first, falls back to generic Amazon Linux 2.
    Cached in Redis for 24 hours.

    architecture: "amd64" (x86_64) or "arm64"
    """
    cache_key = f"dry_run:ami:{region}:{architecture}"
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass

    try:
        import boto3
        ec2 = boto3.client("ec2", region_name=region)

        # Try EKS-optimized AMIs first (AWS account 602401143452)
        if architecture == "arm64":
            eks_name_filter = 'amazon-eks-arm64-node-*'
        else:
            eks_name_filter = 'amazon-eks-node-*'

        resp = ec2.describe_images(
            Owners=['602401143452'],
            Filters=[
                {'Name': 'name', 'Values': [eks_name_filter]},
                {'Name': 'state', 'Values': ['available']},
            ],
        )
        images = sorted(resp.get('Images', []), key=lambda x: x.get('CreationDate', ''), reverse=True)

        if not images:
            # Fallback to generic Amazon Linux 2
            return _get_ami_for_region(ec2, region, redis, architecture)

        ami_id = images[0]['ImageId']
        if redis:
            try:
                redis.setex(cache_key, _AMI_CACHE_TTL, ami_id)
            except Exception:
                pass
        return ami_id
    except Exception as e:
        logger.debug(f"[dry_run] get_eks_ami failed for {region}/{architecture}: {e}")
        return None


def dry_run_pool(
    region: str,
    instance_type: str,
    az: str,
    redis: Optional[Redis] = None,
    credentials: Optional[Dict] = None,
) -> bool:
    """
    Validate ACTUAL spot capacity for instance_type in az via RunInstances DryRun.

    Uses ec2.run_instances(DryRun=True, InstanceMarketOptions=spot) to check real
    spot capacity — not just whether the type is offered in the AZ.

    Returns True if capacity is available, False otherwise.
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

    # Build boto3 client
    try:
        import boto3
        from botocore.exceptions import ClientError

        client_kwargs = {"region_name": region}
        if credentials:
            client_kwargs.update(credentials)
        else:
            try:
                from backend.models.base import get_db
                from backend.models.system_config import SystemConfig
                db = next(get_db())
                try:
                    pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
                    ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
                    if pk and ps and pk.value and ps.value:
                        client_kwargs["aws_access_key_id"] = pk.value
                        client_kwargs["aws_secret_access_key"] = ps.value
                finally:
                    db.close()
            except Exception:
                pass

        ec2 = boto3.client("ec2", **client_kwargs)

        # Detect architecture from instance type family for correct AMI selection
        _ARM64_FAMILIES = {'t4g', 'c6g', 'c7g', 'm6g', 'm7g', 'r6g', 'r7g',
                           'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g'}
        _family = instance_type.split('.')[0] if instance_type else ''
        _arch = "arm64" if _family in _ARM64_FAMILIES else "amd64"

        # Get AMI ID for this region and architecture (needed by run_instances)
        ami_id = _get_ami_for_region(ec2, region, redis, _arch)
        if not ami_id:
            # Fall back to describe_instance_type_offerings if AMI lookup fails
            logger.debug(f"[dry_run] AMI lookup failed for {region}, falling back to offerings check")
            _resp = ec2.describe_instance_type_offerings(
                LocationType="availability-zone",
                Filters=[
                    {"Name": "instance-type", "Values": [instance_type]},
                    {"Name": "location", "Values": [az]},
                ],
            )
            _available = bool(_resp.get("InstanceTypeOfferings"))
            _cache_result(redis, cache_key, _available)
            return _available

        # Real capacity check via RunInstances DryRun=True
        try:
            ec2.run_instances(
                DryRun=True,
                ImageId=ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                Placement={'AvailabilityZone': az},
                InstanceMarketOptions={
                    'MarketType': 'spot',
                    'SpotOptions': {'SpotInstanceType': 'one-time'},
                },
            )
            # Should never reach here — DryRun always raises ClientError
            _cache_result(redis, cache_key, True)
            return True

        except ClientError as ce:
            error_code = ce.response.get("Error", {}).get("Code", "")
            if error_code == "DryRunOperation":
                # Expected success: capacity IS available
                logger.debug(f"[dry_run] {instance_type} in {az}: capacity available (DryRunOperation)")
                _cache_result(redis, cache_key, True)
                return True
            elif error_code == "InsufficientInstanceCapacity":
                logger.info(f"[dry_run] {instance_type} in {az}: InsufficientInstanceCapacity")
                _cache_result(redis, cache_key, False)
                return False
            elif error_code in ("UnauthorizedOperation", "AuthFailure"):
                # DryRun auth check itself passed but we got unauth — treat as available
                # (UnauthorizedOperation on DryRun means the action would be allowed)
                if "DryRun" in str(ce):
                    logger.debug(f"[dry_run] {instance_type} in {az}: capacity available (UnauthorizedOperation+DryRun)")
                    _cache_result(redis, cache_key, True)
                    return True
                logger.warning(f"[dry_run] Auth error for {pool_key}: {error_code} — assuming unavailable")
                _cache_result(redis, cache_key, False)
                return False
            else:
                # Throttle, param error, etc. — conservative fail
                logger.warning(f"[dry_run] {pool_key}: unexpected error {error_code} — assuming unavailable")
                _cache_result(redis, cache_key, False)
                return False

    except Exception as e:
        logger.warning(f"[dry_run] Exception for {pool_key}: {e}")
        return False  # Assume NO capacity on error (conservative)


def _cache_result(redis: Optional[Redis], cache_key: str, passed: bool):
    """Cache dry-run result: pass=600s TTL, fail=300s TTL."""
    if redis:
        try:
            ttl = DRY_RUN_PASS_TTL if passed else DRY_RUN_FAIL_TTL
            redis.setex(cache_key, ttl, "pass" if passed else "fail")
        except Exception:
            pass


def invalidate_dry_run_cache(
    instance_type: str,
    az: str,
    redis: Optional[Redis],
    mark_failed: bool = True,
):
    """
    Immediately invalidate (or mark failed) the dry_run cache for a pool.
    Called when InsufficientInstanceCapacity is caught at launch time.
    """
    if not redis:
        return
    cache_key = f"dry_run:{instance_type}:{az}"
    try:
        if mark_failed:
            redis.setex(cache_key, DRY_RUN_FAIL_TTL, "fail")
            logger.info(f"[dry_run] Marked {instance_type}:{az} as FAIL (capacity error at launch)")
        else:
            redis.delete(cache_key)
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
