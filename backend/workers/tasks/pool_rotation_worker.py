"""
Pool Rotation Worker - Periodic Auto-Rotation Checks
====================================================

Celery Beat task that runs every 5 minutes to:
1. Check pool health for all active clusters
2. Execute auto-rotation if needed
3. Maintain fresh pool cache
4. Activate cascade dampener when necessary

Schedule:
- Runs every 5 minutes (300 seconds)
- Processes all active clusters in parallel
- Logs rotation events to database and Redis
"""

from celery import Task
from sqlalchemy.orm import Session
from redis import Redis

from backend.workers.app import app as celery_app
from backend.core.dependencies import get_database_session
from backend.core.redis_client import get_redis_client
from backend.services.pool_rotation_service import PoolRotationService
from backend.models.cluster import Cluster
from backend.core.logger import logger


class PoolRotationTask(Task):
    """Custom task class with database session management."""

    def __init__(self):
        self._db: Session = None
        self._redis: Redis = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = next(get_database_session())
        return self._db

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    def after_return(self, *args, **kwargs):
        """Clean up database session after task completes."""
        if self._db is not None:
            self._db.close()


@celery_app.task(
    bind=True,
    base=PoolRotationTask,
    name="pool_rotation.check_all_clusters",
    max_retries=3,
    default_retry_delay=60
)
def check_all_clusters_rotation(self):
    """
    Check pool rotation status for all active clusters.

    Runs every 5 minutes via Celery Beat schedule.
    """
    try:
        db = self.db
        redis = self.redis

        # Get all active clusters
        clusters = db.query(Cluster).filter(
            Cluster.status == "ACTIVE"
        ).all()

        if not clusters:
            logger.info("No active clusters found for rotation check")
            return {
                "status": "no_clusters",
                "checked": 0
            }

        logger.info(f"Checking pool rotation for {len(clusters)} active clusters")

        # Initialize service
        service = PoolRotationService(db, redis)

        results = []
        rotations_executed = 0

        # Process each cluster
        for cluster in clusters:
            try:
                # ── Toggle gate: only rotate if auto_rebalance_enabled ────────
                opt_settings = cluster.optimization_settings
                auto_rebalance = getattr(opt_settings, 'auto_rebalance_enabled', False) if opt_settings else False
                if not auto_rebalance:
                    logger.debug(f"Pool rotation skipped for {cluster.name}: auto_rebalance_enabled=False")
                    continue

                result = service.check_and_rotate(
                    cluster_id=cluster.id,
                    region=cluster.region or "ap-south-1"
                )

                if result.get("rotation_executed"):
                    rotations_executed += 1
                    logger.warning(
                        f"Auto-rotation executed for cluster {cluster.id}: "
                        f"{result.get('rotation_result', {}).get('new_primary_az')}"
                    )

                results.append({
                    "cluster_id": cluster.id,
                    "cluster_name": cluster.name,
                    "rotation_executed": result.get("rotation_executed", False),
                    "viable_pools": result.get("pool_status", {}).get("viable_pool_count", 0)
                })

            except Exception as e:
                logger.error(f"Error checking rotation for cluster {cluster.id}: {e}")
                results.append({
                    "cluster_id": cluster.id,
                    "cluster_name": cluster.name,
                    "error": str(e)
                })

        summary = {
            "status": "success",
            "clusters_checked": len(clusters),
            "rotations_executed": rotations_executed,
            "results": results
        }

        logger.info(
            f"Pool rotation check complete: {len(clusters)} clusters checked, "
            f"{rotations_executed} rotations executed"
        )

        return summary

    except Exception as e:
        logger.error(f"Error in check_all_clusters_rotation: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=PoolRotationTask,
    name="pool_rotation.check_single_cluster",
    max_retries=3,
    default_retry_delay=30
)
def check_single_cluster_rotation(self, cluster_id: str, region: str = "ap-south-1"):
    """
    Check pool rotation for a single cluster.

    Can be triggered manually or by events (e.g., blacklist update).

    Args:
        cluster_id: Cluster ID to check
        region: AWS region
    """
    try:
        db = self.db
        redis = self.redis

        service = PoolRotationService(db, redis)
        result = service.check_and_rotate(cluster_id, region)

        if result.get("rotation_executed"):
            logger.warning(
                f"Auto-rotation executed for cluster {cluster_id}: "
                f"{result.get('rotation_result', {}).get('new_primary_az')}"
            )

        return result

    except Exception as e:
        logger.error(f"Error checking rotation for cluster {cluster_id}: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=PoolRotationTask,
    name="pool_rotation.refresh_all_caches",
    max_retries=2
)
def refresh_all_pool_caches(self):
    """
    Proactively refresh fresh pool caches for all clusters.

    Runs every 15 minutes to ensure caches are always fresh.
    """
    try:
        db = self.db
        redis = self.redis

        clusters = db.query(Cluster).filter(
            Cluster.status == "ACTIVE"
        ).all()

        if not clusters:
            return {"status": "no_clusters", "refreshed": 0}

        service = PoolRotationService(db, redis)
        refreshed = 0

        for cluster in clusters:
            try:
                # Get flagging rules
                flagging_rules = service._get_flagging_rules(cluster)

                # Analyze pool health
                pool_status = service._analyze_pool_health(
                    cluster.id,
                    cluster.region or "ap-south-1",
                    flagging_rules
                )

                # Refresh cache
                service._refresh_pool_cache(
                    cluster.id,
                    cluster.region or "ap-south-1",
                    pool_status
                )

                refreshed += 1

            except Exception as e:
                logger.error(f"Error refreshing cache for cluster {cluster.id}: {e}")

        logger.info(f"Refreshed pool caches for {refreshed}/{len(clusters)} clusters")

        return {
            "status": "success",
            "clusters_total": len(clusters),
            "caches_refreshed": refreshed
        }

    except Exception as e:
        logger.error(f"Error in refresh_all_pool_caches: {e}")
        raise self.retry(exc=e)
