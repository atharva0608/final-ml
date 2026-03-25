"""Pool Reputation Service — Step 15 (changes.md)

Computes and maintains a reputation multiplier per spot pool based on historical
LaunchOutcome records.  The multiplier is consumed by Stage 5 (ML Scoring) in
pool_ranking_service.py when building the final_score for each candidate pool.

Redis key: pool_reputation:{pool_key}
  Value: JSON {"success_rate": 0.97, "avg_uptime_hours": 210.5, "sample_count": 42,
               "reputation_mult": 1.10, "updated_at": "2026-03-20T10:00:00"}
  TTL: 3600s — refreshed on every update call

Reputation multiplier tiers (per spec Stage 5.3):
  success_rate >= 0.95 AND avg_uptime > 168h → 1.10   (excellent)
  success_rate >= 0.85                        → 1.05   (good)
  success_rate >= 0.70                        → 0.95   (below-average)
  success_rate <  0.70                        → 0.80   (poor)
  no data yet                                 → 1.00   (neutral)
"""

import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.models.launch_outcome import LaunchOutcome
from backend.core.logger import logger

_REPUTATION_KEY_PREFIX = "pool_reputation:"
_REPUTATION_TTL_S = 3600
_MIN_SAMPLE_THRESHOLD = 3   # Need at least this many outcomes to trust the rate


def _compute_reputation_mult(success_rate: float, avg_uptime_hours: float) -> float:
    """Convert success_rate + avg_uptime into a multiplier per spec Stage 5.3."""
    if success_rate >= 0.95 and avg_uptime_hours > 168:
        return 1.10
    if success_rate >= 0.85:
        return 1.05
    if success_rate >= 0.70:
        return 0.95
    return 0.80


class PoolReputationService:
    """Manages pool reputation data in Redis backed by LaunchOutcome DB records."""

    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_launch_outcome(
        self,
        pool_key: str,
        cluster_id: str,
        instance_type: str,
        az: str,
        region: str,
        outcome: str,
        actual_spot_price_hr: float = None,
        uptime_hours: float = None,
        launched_at: datetime = None,
        resolved_at: datetime = None,
        failure_reason: str = None,
        rebalancing_action_id: int = None,
    ) -> LaunchOutcome:
        """
        Persist a LaunchOutcome row and immediately refresh the Redis reputation key.

        outcome must be one of: 'success', 'failed', 'interrupted'
        """
        if outcome not in ('success', 'failed', 'interrupted'):
            raise ValueError(f"Invalid outcome '{outcome}' — must be success/failed/interrupted")

        row = LaunchOutcome(
            pool_key=pool_key,
            cluster_id=cluster_id,
            instance_type=instance_type,
            az=az,
            region=region,
            outcome=outcome,
            actual_spot_price_hr=actual_spot_price_hr,
            uptime_hours=uptime_hours,
            launched_at=launched_at or datetime.utcnow(),
            resolved_at=resolved_at,
            failure_reason=failure_reason,
            rebalancing_action_id=rebalancing_action_id,
        )
        try:
            self.db.add(row)
            self.db.flush()
            logger.info(
                f"[reputation] Recorded {outcome} for pool={pool_key} "
                f"cluster={cluster_id} action={rebalancing_action_id}"
            )
        except Exception as e:
            logger.error(f"[reputation] Failed to persist LaunchOutcome for {pool_key}: {e}")
            self.db.rollback()
            raise

        # Refresh Redis immediately so the next ranking cycle picks up the new data
        self.update_pool_reputation(pool_key)
        return row

    def update_pool_reputation(self, pool_key: str) -> dict:
        """
        Recompute reputation from DB records for pool_key and write to Redis.
        Uses a 30-day rolling window for relevance.

        Returns the reputation dict.
        """
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = (
            self.db.query(LaunchOutcome)
            .filter(
                LaunchOutcome.pool_key == pool_key,
                LaunchOutcome.launched_at >= cutoff,
            )
            .order_by(LaunchOutcome.launched_at.desc())
            .limit(500)
            .all()
        )

        if not rows or len(rows) < _MIN_SAMPLE_THRESHOLD:
            reputation = {
                "pool_key": pool_key,
                "success_rate": None,
                "avg_uptime_hours": None,
                "sample_count": len(rows),
                "reputation_mult": 1.00,
                "updated_at": datetime.utcnow().isoformat(),
            }
        else:
            success_count = sum(1 for r in rows if r.outcome == 'success')
            success_rate = success_count / len(rows)

            uptime_values = [r.uptime_hours for r in rows if r.uptime_hours is not None]
            avg_uptime = sum(uptime_values) / len(uptime_values) if uptime_values else 0.0

            reputation = {
                "pool_key": pool_key,
                "success_rate": round(success_rate, 4),
                "avg_uptime_hours": round(avg_uptime, 2),
                "sample_count": len(rows),
                "reputation_mult": _compute_reputation_mult(success_rate, avg_uptime),
                "updated_at": datetime.utcnow().isoformat(),
            }

        redis_key = f"{_REPUTATION_KEY_PREFIX}{pool_key}"
        try:
            self.redis.setex(redis_key, _REPUTATION_TTL_S, json.dumps(reputation))
        except Exception as e:
            logger.warning(f"[reputation] Redis write failed for {pool_key}: {e}")

        return reputation

    def get_reputation_multiplier(self, pool_key: str) -> float:
        """
        Return the cached reputation multiplier for pool_key.
        Falls back to 1.00 (neutral) on cache miss or parse error.
        """
        redis_key = f"{_REPUTATION_KEY_PREFIX}{pool_key}"
        try:
            raw = self.redis.get(redis_key)
            if raw:
                data = json.loads(raw)
                return float(data.get("reputation_mult", 1.00))
        except Exception as e:
            logger.debug(f"[reputation] Cache miss/error for {pool_key}: {e}")
        return 1.00

    def get_reputation(self, pool_key: str) -> dict:
        """Return full reputation dict from Redis (or empty dict on miss)."""
        redis_key = f"{_REPUTATION_KEY_PREFIX}{pool_key}"
        try:
            raw = self.redis.get(redis_key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return {}

    def bulk_get_multipliers(self, pool_keys: list) -> dict:
        """
        Batch-fetch reputation multipliers for a list of pool_keys.
        Returns {pool_key: multiplier} mapping.  Missing keys default to 1.00.
        """
        if not pool_keys:
            return {}

        redis_keys = [f"{_REPUTATION_KEY_PREFIX}{pk}" for pk in pool_keys]
        try:
            values = self.redis.mget(*redis_keys)
        except Exception as e:
            logger.warning(f"[reputation] bulk_get_multipliers mget failed: {e}")
            return {pk: 1.00 for pk in pool_keys}

        result = {}
        for pk, raw in zip(pool_keys, values):
            if raw:
                try:
                    result[pk] = float(json.loads(raw).get("reputation_mult", 1.00))
                    continue
                except Exception:
                    pass
            result[pk] = 1.00
        return result
