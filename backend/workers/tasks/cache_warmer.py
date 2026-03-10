"""
Cache Warmer — Periodic Pre-computation of Pool Rankings
=========================================================

Celery periodic task (hourly) that pre-computes and caches ML pool rankings
for the most common node profiles observed across active clusters.

This eliminates cold-start latency when the Decision Engine receives
ranking requests for common profiles.
"""

from backend.core.logger import logger
from backend.workers.app import app


@app.task(name="cache_warmer", bind=True, max_retries=1)
def cache_warmer(self):
    """
    Pre-warm pool rankings cache for common node profiles.

    Logic:
    1. Query DB for all active clusters.
    2. Collect unique instance types currently running across clusters.
    3. Group by (vcpu, memory) profile to find the most common profiles.
    4. For each common profile, call PoolRankingService to generate
       and cache rankings (stored under pool_rankings:{region}:{profile_hash}).
    """
    import hashlib
    import json
    from collections import Counter
    from backend.models.base import get_db
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.core.redis_client import get_redis_client
    from backend.services.pool_ranking_service import PoolRankingService

    db = next(get_db())
    redis = get_redis_client()

    try:
        # 1. Get active clusters
        clusters = db.query(Cluster).filter(
            Cluster.status == "active"
        ).all()

        if not clusters:
            logger.info("[cache_warmer] No active clusters, skipping warm-up")
            return {"status": "no_clusters"}

        # 2. Collect instance types from running nodes
        running_instances = db.query(Instance).filter(
            Instance.state == "running"
        ).all()

        if not running_instances:
            logger.info("[cache_warmer] No running instances, skipping warm-up")
            return {"status": "no_instances"}

        # 3. Build profile frequency map
        profile_counter = Counter()
        profile_to_params = {}

        svc = PoolRankingService(db, redis)
        catalog = svc.instance_catalog

        for inst in running_instances:
            specs = catalog.get(inst.instance_type, {})
            vcpu = specs.get("vcpu", 2)
            memory = specs.get("memory_gb", 4)
            profile_key = f"{vcpu}:{int(memory)}"
            profile_counter[profile_key] += 1
            if profile_key not in profile_to_params:
                profile_to_params[profile_key] = {"vcpu": vcpu, "memory_gb": memory}

        # 4. Pre-warm rankings for top 10 most common profiles
        warmed = 0
        for profile_key, count in profile_counter.most_common(10):
            params = profile_to_params[profile_key]
            try:
                # Get unique regions from clusters
                regions = set()
                for c in clusters:
                    regions.add(c.region or "ap-south-1")

                for region in regions:
                    ph = hashlib.md5(
                        f"{params['vcpu']}:{int(params['memory_gb'])}:[]:[]".encode()
                    ).hexdigest()[:12]
                    cache_key = f"pool_rankings:{region}:{ph}"

                    # Skip if already cached
                    if redis.exists(cache_key):
                        continue

                    pools = svc.rank_pools_for_size(
                        vcpu=params["vcpu"],
                        memory_gb=params["memory_gb"],
                        region=region,
                        limit=20,
                    )

                    if pools:
                        cache_data = [
                            {
                                "instance_type": p.pool.instance_type,
                                "az": p.pool.az,
                                "vcpu": p.pool.vcpu,
                                "memory_gb": p.pool.memory_gb,
                                "spot_price": p.pool.spot_price,
                                "ondemand_price": p.pool.ondemand_price,
                                "predicted_savings": p.predicted_savings,
                                "risk_probability": p.risk_probability,
                                "ml_score": p.ml_score,
                                "rank": p.rank,
                                "is_flagged": p.is_flagged,
                                "pool_key": f"{p.pool.instance_type}:{p.pool.az}",
                            }
                            for p in pools
                        ]
                        redis.setex(cache_key, 3600, json.dumps(cache_data))
                        warmed += 1
                        logger.info(
                            f"[cache_warmer] Warmed {cache_key}: "
                            f"{len(pools)} pools for {params['vcpu']}vCPU/{params['memory_gb']}GB"
                        )

            except Exception as e:
                logger.warning(f"[cache_warmer] Failed for profile {profile_key}: {e}")

        logger.info(f"[cache_warmer] Complete: warmed {warmed} profile/region combos")
        return {"status": "ok", "warmed": warmed}

    except Exception as e:
        logger.error(f"[cache_warmer] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
