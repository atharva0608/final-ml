"""
Adaptive ITN Celery Tasks
=========================

``accumulate_global_node_hours`` — hourly (C6): for every running/pending spot
node across ALL clusters, atomically increment
``global_pool_ledger:{pool_key}:node_hours`` by 1.0 via INCRBYFLOAT.
Runs at :55 so the accumulator is fully populated before the decay task fires.

``decay_adaptive_itn_scores`` — hourly: reads the accumulated node-hours,
decays raw interruption scores for every pool, and flushes to Postgres.
"""

import logging

from backend.workers.app import app

logger = logging.getLogger(__name__)


@app.task(name="adaptive_itn.accumulate_node_hours")
def accumulate_global_node_hours():
    """
    C6 — Hourly accumulation task.

    For every running/pending spot node across ALL clusters:
      pool_key = "{instance_type}:{az}"
      INCRBYFLOAT global_pool_ledger:{pool_key}:node_hours 1.0

    Counts are aggregated in Python first so we make one INCRBYFLOAT call per
    unique pool rather than one per node, minimising Redis round-trips.
    INCRBYFLOAT is atomic so multiple Celery workers cannot produce a race condition.
    """
    from backend.core.redis_client import get_redis_client
    from backend.models.base import SessionLocal
    from backend.models.instance import Instance

    redis_client = get_redis_client()
    db = SessionLocal()
    try:
        rows = (
            db.query(Instance.instance_type, Instance.az)
            .filter(
                Instance.state.in_(["running", "pending"]),
                Instance.instance_type.isnot(None),
                Instance.az.isnot(None),
            )
            .all()
        )

        pool_counts: dict = {}
        for row in rows:
            pk = f"{row.instance_type}:{row.az}"
            pool_counts[pk] = pool_counts.get(pk, 0.0) + 1.0

        for pool_key, count in pool_counts.items():
            redis_client.incrbyfloat(
                f"global_pool_ledger:{pool_key}:node_hours", count
            )

        logger.info(
            f"[adaptive_itn.accumulate_node_hours] Incremented {len(pool_counts)} pools "
            f"({sum(pool_counts.values()):.0f} total node-hours)"
        )
    except Exception as exc:
        logger.error(f"[adaptive_itn.accumulate_node_hours] Failed: {exc}")
        raise
    finally:
        db.close()


@app.task(name="adaptive_itn.decay_scores")
def decay_adaptive_itn_scores():
    """
    Hourly decay task for the adaptive interruption ledger.

    For every ``global_pool_ledger:*`` key in Redis (C1 — global, no cluster_id):
      1. Compute elapsed hours since ``last_updated``.
      2. Increment ``node_hours_observed`` by elapsed hours.
      3. Recompute ``confidence = 1 - exp(-node_hours_observed / TAU)``.
      4. Apply score decay: ``raw_itn_score *= exp(-hours_since_last_itn / STABILITY_HALF_LIFE)``.
      5. Write ledger back to Redis.
      6. Upsert ledger into Postgres (durable backup).
    """
    from backend.core.redis_client import get_redis_client
    from backend.services.adaptive_itn_service import AdaptiveItnService, _parse_iso, _now_utc

    redis_client = get_redis_client()
    now = _now_utc()

    try:
        cursor = 0
        processed = 0
        errors = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="global_pool_ledger:*", count=200)
            for raw_key in keys:
                pool_key = (
                    raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                ).removeprefix("global_pool_ledger:")
                try:
                    raw = redis_client.get(f"global_pool_ledger:{pool_key}")
                    if not raw:
                        continue
                    import json
                    ledger = json.loads(raw)
                    last_updated = _parse_iso(ledger.get("last_updated"))
                    elapsed_hours = (
                        (now - last_updated).total_seconds() / 3600.0
                        if last_updated
                        else 1.0
                    )
                    updated_ledger = AdaptiveItnService.apply_hourly_decay(
                        pool_key, redis_client, elapsed_hours=elapsed_hours
                    )
                    AdaptiveItnService.flush_to_postgres(pool_key, updated_ledger)
                    processed += 1
                except Exception as e:
                    logger.warning(f"[adaptive_itn.decay] Error processing {pool_key}: {e}")
                    errors += 1
            if cursor == 0:
                break
        logger.info(
            f"[adaptive_itn.decay] Completed: processed={processed} errors={errors}"
        )
    except Exception as exc:
        logger.error(f"[adaptive_itn.decay] Task failed: {exc}")
        raise
