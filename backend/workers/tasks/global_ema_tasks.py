"""
Global EMA Celery Tasks
========================

``persist_global_pool_ema`` — asynchronous DB upsert after Redis update.
``global_ema_decay``        — daily background decay of all pool EMA entries.
"""

import logging
from backend.workers.app import app

logger = logging.getLogger(__name__)


@app.task(name="global_ema.persist", bind=True, max_retries=2, default_retry_delay=10)
def persist_global_pool_ema(self, pool_key: str, stats: dict, region: str, instance_type: str, az: str):
    """
    Async upsert of EMA stats into Postgres.
    Enqueued by ``global_ema_service.update_ema_on_interruption``.
    """
    from backend.models.base import get_db
    from backend.services.global_ema_service import _persist_to_db

    db = next(get_db())
    try:
        _persist_to_db(db, pool_key, stats, region, instance_type, az)
        logger.debug(f"[ema-task] Persisted EMA for {pool_key}")
    except Exception as exc:
        db.rollback()
        logger.warning(f"[ema-task] persist failed for {pool_key}: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@app.task(name="global_ema.decay", bind=True, max_retries=0)
def global_ema_decay(self):
    """
    Daily background job: apply exponential decay to all pool EMA entries.
    Runs via Celery beat schedule (daily at 2 AM).
    """
    from backend.models.base import get_db
    from backend.core.redis_client import get_redis_client
    from backend.services.global_ema_service import decay_all_pools

    db = next(get_db())
    redis = get_redis_client()
    try:
        processed = decay_all_pools(redis, db)
        logger.info(f"[ema-task] Decay job complete: {processed} entries processed")
        return {"status": "ok", "processed": processed}
    except Exception as exc:
        logger.error(f"[ema-task] Decay job failed: {exc}")
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
