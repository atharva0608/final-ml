"""
Global EMA Service
==================

Manages the global, cross-customer EMA interruption tracker for spot pools.

EMA state is dual-stored:
  - Redis (hot cache): ``global:pool:interruption:{pool_key}``  TTL 90 days
  - PostgreSQL (durable): ``global_pool_ema`` table

Key operations:
  - ``get_or_create_ema``   — lazily initialise a pool entry on first spot launch
  - ``update_ema_on_interruption`` — update after a spot interruption event
  - ``apply_decay``         — apply time-based exponential decay (30-day half-life)
  - ``persist_to_db``       — upsert Redis state into Postgres
  - ``get_ema_stats``       — read-through: Redis → DB fallback

Formulas (from changes.md §4):
  * Decay: ``value *= 0.5 ** (days / 30.0)``
  * EMA update: ``new_rate = old_rate × (1 - α) + max_rate × α``  where α = 0.1
  * Confidence: ``1.0 - 0.5 ** (count / 200.0)``  capped at 0.95
  * EMA weight for risk blend: ``confidence × 0.40``  (max 40%)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from redis import Redis
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────
EMA_ALPHA = 0.1           # EMA smoothing factor
MAX_RATE = 25.0            # Spot Advisor maximum interruption rate
DECAY_HALF_LIFE_DAYS = 30  # 30-day half-life for exponential decay
REDIS_TTL_SECONDS = 90 * 86400  # 90 days


def _redis_key(pool_key: str) -> str:
    return f"global:pool:interruption:{pool_key}"


def _cluster_set_key(pool_key: str) -> str:
    return f"global:pool:interruption:{pool_key}:clusters"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Read / Create ────────────────────────────────────────────────────────

def get_ema_stats(redis: Redis, db: Session, pool_key: str) -> Optional[Dict[str, Any]]:
    """
    Read EMA stats with read-through cache:  Redis → DB → None.
    Returns dict with keys: count, rate, peak_rate, last_updated, last_event, sample_clusters.
    """
    raw = redis.get(_redis_key(pool_key))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass

    # Fallback to DB
    from backend.models.global_pool_ema import GlobalPoolEMA
    row = db.query(GlobalPoolEMA).filter(GlobalPoolEMA.pool_key == pool_key).first()
    if row:
        stats = {
            "count": row.count,
            "rate": float(row.rate),
            "peak_rate": float(row.peak_rate),
            "last_updated": row.updated_at.isoformat() if row.updated_at else _now_iso(),
            "last_event": row.last_event.isoformat() if row.last_event else None,
            "sample_clusters": row.sample_clusters,
        }
        # Restore Redis cache
        redis.setex(_redis_key(pool_key), REDIS_TTL_SECONDS, json.dumps(stats))
        return stats

    return None


def get_or_create_ema(
    redis: Redis,
    db: Session,
    pool_key: str,
    instance_type: str,
    az: str,
    region: str,
) -> Dict[str, Any]:
    """
    Get existing EMA entry, or create a neutral one (count=0, rate=0).
    Called on first spot launch for a pool.
    """
    existing = get_ema_stats(redis, db, pool_key)
    if existing:
        return existing

    stats = {
        "count": 0,
        "rate": 0.0,
        "peak_rate": 0.0,
        "last_updated": _now_iso(),
        "last_event": None,
        "sample_clusters": 0,
    }
    redis.setex(_redis_key(pool_key), REDIS_TTL_SECONDS, json.dumps(stats))

    # Persist to DB (synchronous here — lightweight insert)
    from backend.models.global_pool_ema import GlobalPoolEMA
    row = GlobalPoolEMA(
        pool_key=pool_key,
        instance_type=instance_type,
        az=az,
        region=region,
        count=0,
        rate=0.0,
        peak_rate=0.0,
        sample_clusters=0,
        last_event=None,
    )
    try:
        db.merge(row)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[ema] Failed to persist new EMA entry for {pool_key}: {e}")

    logger.info(f"[ema] Created neutral EMA entry for {pool_key}")
    return stats


# ── Decay ────────────────────────────────────────────────────────────────

def apply_decay(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply time-based exponential decay to EMA stats.
    Decay factor: ``0.5 ** (days / 30.0)``  → rate halves every 30 days.
    Mutates and returns the same dict.
    """
    last_updated = _parse_iso(stats.get("last_updated"))
    if not last_updated:
        stats["last_updated"] = _now_iso()
        return stats

    now = datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        from datetime import timezone as _tz
        last_updated = last_updated.replace(tzinfo=_tz.utc)

    days = (now - last_updated).total_seconds() / 86400.0
    if days < 1.0:
        return stats

    decay = 0.5 ** (days / DECAY_HALF_LIFE_DAYS)
    stats["count"] = int(stats.get("count", 0) * decay)
    stats["rate"] = round(float(stats.get("rate", 0.0)) * decay, 4)
    stats["peak_rate"] = round(float(stats.get("peak_rate", 0.0)) * decay, 4)
    stats["last_updated"] = _now_iso()
    return stats


# ── Interruption Update ──────────────────────────────────────────────────

def update_ema_on_interruption(
    redis: Redis,
    db: Session,
    pool_key: str,
    instance_type: str,
    az: str,
    region: str,
    cluster_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update EMA after a spot interruption event.

    Steps (from changes.md §4.2):
      1. Apply time decay
      2. EMA update: new_rate = old_rate × (1 - α) + max_rate × α
      3. Update sample_clusters
      4. Store in Redis + enqueue DB persist
    """
    stats = get_or_create_ema(redis, db, pool_key, instance_type, az, region)

    # Step 1: time decay
    apply_decay(stats)

    # Step 2: EMA update
    old_rate = float(stats.get("rate", 0.0))
    new_rate = old_rate * (1 - EMA_ALPHA) + MAX_RATE * EMA_ALPHA
    new_count = int(stats.get("count", 0)) + 1
    new_peak = max(float(stats.get("peak_rate", 0.0)), new_rate)

    stats["rate"] = round(new_rate, 4)
    stats["count"] = new_count
    stats["peak_rate"] = round(new_peak, 4)
    stats["last_event"] = _now_iso()
    stats["last_updated"] = _now_iso()

    # Step 3: update sample_clusters
    if cluster_id:
        redis.sadd(_cluster_set_key(pool_key), cluster_id)
        stats["sample_clusters"] = redis.scard(_cluster_set_key(pool_key))

    # Step 4: store in Redis
    redis.setex(_redis_key(pool_key), REDIS_TTL_SECONDS, json.dumps(stats))

    # Enqueue async DB persist
    try:
        from backend.workers.tasks.global_ema_tasks import persist_global_pool_ema
        persist_global_pool_ema.delay(pool_key, stats, region, instance_type, az)
    except Exception as e:
        logger.warning(f"[ema] Failed to enqueue DB persist for {pool_key}: {e}")
        # Fallback: persist synchronously
        _persist_to_db(db, pool_key, stats, region, instance_type, az)

    logger.info(
        f"[ema] Updated {pool_key}: rate={new_rate:.2f}, count={new_count}, "
        f"peak={new_peak:.2f}, clusters={stats.get('sample_clusters', 0)}"
    )
    return stats


def _persist_to_db(
    db: Session,
    pool_key: str,
    stats: Dict[str, Any],
    region: str,
    instance_type: str,
    az: str,
):
    """Synchronous upsert of EMA stats into Postgres."""
    from backend.models.global_pool_ema import GlobalPoolEMA

    row = db.query(GlobalPoolEMA).filter(GlobalPoolEMA.pool_key == pool_key).first()
    if not row:
        row = GlobalPoolEMA(
            pool_key=pool_key,
            instance_type=instance_type,
            az=az,
            region=region,
        )
        db.add(row)

    row.count = int(stats.get("count", 0))
    row.rate = round(float(stats.get("rate", 0.0)), 2)
    row.peak_rate = round(float(stats.get("peak_rate", 0.0)), 2)
    row.sample_clusters = int(stats.get("sample_clusters", 0))
    last_event = _parse_iso(stats.get("last_event"))
    if last_event:
        row.last_event = last_event.replace(tzinfo=None)
    row.updated_at = datetime.utcnow()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[ema] DB persist failed for {pool_key}: {e}")


# ── Decay All (Background Job) ──────────────────────────────────────────

def decay_all_pools(redis: Redis, db: Session) -> int:
    """
    Background job: apply time decay to ALL pool EMA entries in Redis.
    Returns the number of entries processed.

    Called daily by Celery beat task ``global_ema_decay``.
    """
    cursor = 0
    pattern = "global:pool:interruption:*"
    processed = 0

    while True:
        cursor, keys = redis.scan(cursor, match=pattern, count=200)
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Skip cluster set keys
            if key_str.endswith(":clusters"):
                continue

            try:
                raw = redis.get(key_str)
                if not raw:
                    continue
                stats = json.loads(raw)
                old_rate = float(stats.get("rate", 0.0))

                apply_decay(stats)

                # Only rewrite if decay actually changed the rate
                new_rate = float(stats.get("rate", 0.0))
                if abs(old_rate - new_rate) > 0.001:
                    redis.setex(key_str, REDIS_TTL_SECONDS, json.dumps(stats))

                    # Also update DB
                    pool_key = key_str.replace("global:pool:interruption:", "")
                    from backend.models.global_pool_ema import GlobalPoolEMA
                    row = db.query(GlobalPoolEMA).filter(
                        GlobalPoolEMA.pool_key == pool_key
                    ).first()
                    if row:
                        row.count = int(stats.get("count", 0))
                        row.rate = round(float(stats.get("rate", 0.0)), 2)
                        row.peak_rate = round(float(stats.get("peak_rate", 0.0)), 2)
                        row.updated_at = datetime.utcnow()

                processed += 1
            except Exception as e:
                logger.debug(f"[ema] Decay failed for {key_str}: {e}")

        if cursor == 0:
            break

    try:
        db.commit()
    except Exception:
        db.rollback()

    logger.info(f"[ema] Decay job processed {processed} pool entries")
    return processed


# ── Helpers for Unified Score ────────────────────────────────────────────

def get_ema_risk(redis: Redis, db: Session, pool_key: str) -> tuple:
    """
    Returns (ema_risk, ema_weight) for risk blending.

    ema_risk  = min(1.0, ema_rate / 25.0)
    ema_weight = confidence × 0.40   where confidence = 1.0 - 0.5^(count/200)

    If no EMA data exists, returns (0.0, 0.0) — no EMA influence.
    """
    stats = get_ema_stats(redis, db, pool_key)
    if not stats or stats.get("count", 0) == 0:
        return 0.0, 0.0

    apply_decay(stats)

    ema_rate = float(stats.get("rate", 0.0))
    ema_count = int(stats.get("count", 0))

    ema_risk = min(1.0, ema_rate / MAX_RATE)
    confidence = min(0.95, 1.0 - 0.5 ** (ema_count / 200.0))
    ema_weight = confidence * 0.40  # EMA never exceeds 40%

    return ema_risk, ema_weight
