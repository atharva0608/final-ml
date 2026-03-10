"""
Dry-Run Refresher — Periodic Refresh of Pool Capacity Status
=============================================================

Celery periodic task (every 5 minutes) that refreshes the dry-run cache
for the top 100 globally ranked pools. This ensures that when the
Decision Engine returns rankings, the capacity status is fresh.
"""

from backend.core.logger import logger
from backend.workers.app import app


@app.task(name="dry_run_refresher", bind=True, max_retries=1)
def dry_run_refresher(self):
    """
    Refresh dry-run results for top 100 globally ranked pools.

    Logic:
    1. Read the global ranking cache from Redis.
    2. For the top 100 pools, call RunInstances DryRun.
    3. Update dry_run:{pool_key} cache entries.
    """
    from backend.core.redis_client import get_redis_client
    from backend.utils.aws.dry_run import dry_run_pool

    redis = get_redis_client()

    try:
        # Get globally cached rankings
        cached_raw = redis.get("atharvaai:pool_rankings")
        if not cached_raw:
            logger.info("[dry_run_refresher] No global rankings cached, skipping")
            return {"status": "no_rankings"}

        import json
        pools = json.loads(cached_raw)
        top_pools = pools[:100]

        refreshed = 0
        passed = 0
        failed = 0

        for p in top_pools:
            instance_type = p.get("instance_type")
            az = p.get("az")
            if not instance_type or not az:
                continue

            # Determine region from AZ (e.g., "ap-south-1a" → "ap-south-1")
            region = az[:-1] if az and len(az) > 1 else "ap-south-1"

            result = dry_run_pool(
                region=region,
                instance_type=instance_type,
                az=az,
                redis=redis,
            )

            refreshed += 1
            if result:
                passed += 1
            else:
                failed += 1

        logger.info(
            f"[dry_run_refresher] Refreshed {refreshed} pools: "
            f"{passed} passed, {failed} failed"
        )
        return {"status": "ok", "refreshed": refreshed, "passed": passed, "failed": failed}

    except Exception as e:
        logger.error(f"[dry_run_refresher] Failed: {e}")
        return {"status": "error", "error": str(e)}
