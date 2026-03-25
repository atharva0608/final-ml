"""
Dry-Run Refresher — Periodic Refresh of Pool Capacity Status
=============================================================

Celery periodic task (every 5 minutes) that refreshes the dry-run cache
for the top 100 globally ranked pools. This ensures that when the
Decision Engine returns rankings, the capacity status is fresh.

Also maintains a per-cluster verified_pools ZSET so the execution engine
always has capacity-confirmed pools ready without synchronous dry runs.
"""

import time
import json

from backend.core.logger import logger
from backend.workers.app import app

# Target size for verified pool ZSET per cluster
_VERIFIED_POOL_TARGET = 20
# TTL for verified_pools ZSET expiry key (refreshed each cycle)
_VERIFIED_SET_TTL = 3600


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
        cached_raw = redis.get("ascpai:pool_rankings")
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

            # Rate limit: 2 calls/sec max
            time.sleep(0.5)

        logger.info(
            f"[dry_run_refresher] Refreshed {refreshed} pools: "
            f"{passed} passed, {failed} failed"
        )
        return {"status": "ok", "refreshed": refreshed, "passed": passed, "failed": failed}

    except Exception as e:
        logger.error(f"[dry_run_refresher] Failed: {e}")
        return {"status": "error", "error": str(e)}


@app.task(name="run_dry_run_checks", bind=True, max_retries=1)
def run_dry_run_checks(self, cluster_id: str, pool_keys: list):
    """
    On-demand dry run checks for specific pool_keys for a cluster.

    pool_keys format: ["instance_type:az", ...]  e.g. ["t3a.medium:ap-south-1a"]

    Triggered by:
    - POST /clusters/{cluster_id}/dry-run-check endpoint (Market View page load)
    - After cache builder completes (bulk top-50 per cluster)
    - Before execution engine launches (automatic in auto_rebalancer)

    Rate limit: 0.5s between calls (2/sec max).
    """
    from backend.core.redis_client import get_redis_client
    from backend.utils.aws.dry_run import dry_run_pool

    redis = get_redis_client()
    passed = 0
    failed = 0
    skipped = 0

    try:
        for pool_key in pool_keys:
            # Skip if recently cached — avoid redundant API calls
            cached = redis.get(f"dry_run:{pool_key}")
            if cached:
                skipped += 1
                continue

            # Parse pool_key: "instance_type:az"
            parts = pool_key.split(":")
            if len(parts) != 2:
                logger.warning(f"[run_dry_run_checks] Invalid pool_key format: {pool_key}")
                continue

            instance_type, az = parts
            region = az[:-1] if len(az) > 1 else "ap-south-1"

            try:
                result = dry_run_pool(
                    region=region,
                    instance_type=instance_type,
                    az=az,
                    redis=redis,
                )
                if result:
                    passed += 1
                else:
                    failed += 1
                    # Report to pool ranking service so blacklist scoring tracks it
                    try:
                        from backend.services.pool_ranking_service import report_launch_failure as _rlf
                        _rlf(pool_key)
                    except Exception:
                        pass
            except Exception as pool_err:
                logger.warning(f"[run_dry_run_checks] Error for {pool_key}: {pool_err}")

            # Rate limit: 2 calls/sec max
            time.sleep(0.5)

        logger.info(
            f"[run_dry_run_checks] cluster={cluster_id} "
            f"passed={passed} failed={failed} skipped={skipped}"
        )
        return {
            "status": "ok",
            "cluster_id": cluster_id,
            "passed": passed,
            "failed": failed,
            "skipped_cached": skipped,
        }

    except Exception as e:
        logger.error(f"[run_dry_run_checks] cluster={cluster_id} error: {e}")
        return {"status": "error", "error": str(e)}


@app.task(name="maintain_verified_pool_set", bind=True, max_retries=1)
def maintain_verified_pool_set(self, cluster_id: str, target_size: int = _VERIFIED_POOL_TARGET):
    """
    Maintain a per-cluster verified_pools ZSET in Redis.

    Key: verified_pools:{cluster_id}  (Redis ZSET, score = final_score)

    Invariant: Always holds at least target_size pools that:
      1. Are in the current global ranked list for the cluster's region
      2. Pass dry-run capacity check (dry_run:{pool_key} == "pass")
      3. Are not in the blacklist (risky_pools:{region})

    When pools are eliminated (dry-run fail or blacklist), this task
    promotes the next-best candidates to fill the gap.

    Triggered every 5 minutes via beat, and on-demand after dry-run failures.
    """
    from backend.core.redis_client import get_redis_client
    from backend.utils.aws.dry_run import dry_run_pool
    from backend.models.base import get_db
    from backend.models.cluster import Cluster

    redis = get_redis_client()
    db = next(get_db())

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return {"status": "error", "error": f"Cluster {cluster_id} not found"}

        region = cluster.region or "ap-south-1"
        verified_key = f"verified_pools:{cluster_id}"
        blacklist_key = f"risky_pools:{region}"

        # ── Step 1: Remove stale entries from verified set ──────────────────
        existing = redis.zrange(verified_key, 0, -1)
        for pool_key_b in existing:
            pool_key = pool_key_b.decode() if isinstance(pool_key_b, bytes) else pool_key_b
            # Remove if blacklisted
            if redis.sismember(blacklist_key, pool_key) or redis.sismember("risky_pools", pool_key):
                redis.zrem(verified_key, pool_key)
                continue
            # Remove if dry-run cache shows fail
            cached = redis.get(f"dry_run:{pool_key}")
            if cached and (cached.decode() if isinstance(cached, bytes) else cached) == "fail":
                redis.zrem(verified_key, pool_key)

        # ── Step 2: Check how many verified pools remain ────────────────────
        current_count = redis.zcard(verified_key)
        needed = target_size - current_count
        if needed <= 0:
            redis.expire(verified_key, _VERIFIED_SET_TTL)
            return {"status": "ok", "cluster_id": cluster_id, "verified_count": current_count, "filled": 0}

        # ── Step 3: Load global ranked list for this region ─────────────────
        ranked_raw = redis.get(f"global_pool_rankings:{region}") or redis.get("ascpai:pool_rankings")
        if not ranked_raw:
            return {"status": "no_rankings", "cluster_id": cluster_id}

        try:
            all_pools = json.loads(ranked_raw)
        except Exception:
            return {"status": "error", "error": "bad_rankings_json"}

        # ── Step 4: Build set of already-verified pool_keys ─────────────────
        verified_keys = set()
        for pk_b in redis.zrange(verified_key, 0, -1):
            verified_keys.add(pk_b.decode() if isinstance(pk_b, bytes) else pk_b)

        # ── Step 5: Find candidates not yet verified and not known-failed ────
        candidates = []
        for p in all_pools:
            itype = p.get("instance_type")
            az = p.get("az")
            if not itype or not az:
                continue
            pk = f"{itype}:{az}"
            if pk in verified_keys:
                continue
            cached = redis.get(f"dry_run:{pk}")
            if cached and (cached.decode() if isinstance(cached, bytes) else cached) == "fail":
                continue
            if redis.sismember(blacklist_key, pk) or redis.sismember("risky_pools", pk):
                continue
            candidates.append((pk, itype, az, float(p.get("final_score", p.get("score", 0.5)))))

        # ── Step 6: Dry-run up to 'needed' candidates to fill the gap ────────
        filled = 0
        for pk, itype, az, score in candidates[:needed * 2]:  # extra headroom for failures
            if filled >= needed:
                break
            pool_region = az[:-1] if len(az) > 1 else region
            result = dry_run_pool(region=pool_region, instance_type=itype, az=az, redis=redis)
            if result:
                redis.zadd(verified_key, {pk: score})
                filled += 1
            # Rate limit
            time.sleep(0.5)

        redis.expire(verified_key, _VERIFIED_SET_TTL)
        final_count = redis.zcard(verified_key)

        if final_count < 3:
            logger.warning(
                f"[verified_pools] Cluster {cluster_id}: only {final_count} verified pools "
                f"— limited spot options"
            )
        else:
            logger.info(
                f"[verified_pools] Cluster {cluster_id}: {final_count} verified pools "
                f"(filled {filled} gaps)"
            )

        return {
            "status": "ok",
            "cluster_id": cluster_id,
            "verified_count": final_count,
            "filled": filled,
        }

    except Exception as e:
        logger.error(f"[verified_pools] cluster={cluster_id} error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


@app.task(name="maintain_all_verified_pool_sets", bind=True, max_retries=1)
def maintain_all_verified_pool_sets(self):
    """
    Run maintain_verified_pool_set for all active clusters.
    Called every 5 minutes via Celery beat.
    """
    from backend.models.base import get_db
    from backend.models.cluster import Cluster, ClusterStatus

    db = next(get_db())
    results = {}
    try:
        clusters = db.query(Cluster).filter(Cluster.status == ClusterStatus.ACTIVE).all()
        for cluster in clusters:
            try:
                r = maintain_verified_pool_set.apply(args=[cluster.id])
                results[cluster.id] = r.result
            except Exception as ce:
                results[cluster.id] = {"status": "error", "error": str(ce)}
        return {"status": "ok", "clusters": len(clusters), "results": results}
    except Exception as e:
        logger.error(f"[maintain_all_verified_pool_sets] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
