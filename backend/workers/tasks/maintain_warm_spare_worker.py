"""
Warm Spare Maintenance Worker
==============================

Runs every 5 minutes to ensure each cluster with auto_rebalance_enabled=True
has at least 1 warm substitute node running 24x7.

The warm spare is:
  - Sized for the LARGEST node in the cluster (compatible with every node)
  - The CHEAPEST available spot pool for those specs
  - Always READY — no timeout, stays running until it is used or specs change
  - When used (ACTIVE): immediately spins up a replacement spare
  - When the largest node changes: automatically re-provisions with correct size
"""

from celery import Task
from sqlalchemy.orm import Session
from redis import Redis

from backend.workers.app import app as celery_app
from backend.core.dependencies import get_database_session
from backend.core.redis_client import get_redis_client
from backend.services.substitute_manager import SubstituteManager
from backend.models.cluster import Cluster
from backend.core.logger import logger


class WarmSpareTask(Task):
    """Task class with lazy DB/Redis session management."""

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
        if self._db is not None:
            self._db.close()


@celery_app.task(
    bind=True,
    base=WarmSpareTask,
    name="warm_spare.maintain_all_clusters",
    max_retries=3,
    default_retry_delay=60
)
def maintain_warm_spare_all_clusters(self):
    """
    Ensure ≥1 warm spare for every auto-rebalance-enabled cluster.

    Called every 5 minutes by Celery Beat.
    """
    try:
        db = self.db
        redis = self.redis

        clusters = db.query(Cluster).filter(Cluster.status == "ACTIVE").all()
        if not clusters:
            return {"status": "no_clusters", "processed": 0}

        manager = SubstituteManager(db, redis)
        results = []
        provisioned = 0

        for cluster in clusters:
            try:
                opt = cluster.optimization_settings
                auto_rebalance = getattr(opt, "auto_rebalance_enabled", False) if opt else False
                if not auto_rebalance:
                    continue

                region = cluster.region or "ap-south-1"
                result = manager.ensure_warm_spare(cluster.id, region)

                if result.get("status") in ("provisioned", "replacement_prewarming"):
                    provisioned += 1
                    logger.info(
                        f"[warm-spare] {result['status']} for {cluster.name}: "
                        f"{result.get('spare_instance_type','?')} "
                        f"in {result.get('spare_az','?')}"
                    )

                results.append({
                    "cluster_id": cluster.id,
                    "cluster_name": cluster.name,
                    "result": result.get("status"),
                    "spare_type": result.get("spare_instance_type"),
                })

            except Exception as e:
                logger.error(f"[warm-spare] Error for cluster {cluster.id}: {e}")
                results.append({"cluster_id": cluster.id, "error": str(e)})

        logger.info(
            f"[warm-spare] Cycle complete: {len(results)} clusters checked, "
            f"{provisioned} spares provisioned/updated"
        )
        return {
            "status": "success",
            "clusters_checked": len(results),
            "spares_provisioned": provisioned,
            "results": results,
        }

    except Exception as e:
        logger.error(f"[warm-spare] Fatal error in maintain_warm_spare_all_clusters: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=WarmSpareTask,
    name="warm_spare.maintain_single_cluster",
    max_retries=3,
    default_retry_delay=30
)
def maintain_warm_spare_single_cluster(self, cluster_id: str, region: str = "ap-south-1"):
    """
    Ensure warm spare for a single cluster (triggered on-demand or after promotion).
    """
    try:
        manager = SubstituteManager(self.db, self.redis)
        result = manager.ensure_warm_spare(cluster_id, region)
        logger.info(f"[warm-spare] Single cluster {cluster_id}: {result.get('status')}")
        return result
    except Exception as e:
        logger.error(f"[warm-spare] Error for cluster {cluster_id}: {e}")
        raise self.retry(exc=e)
