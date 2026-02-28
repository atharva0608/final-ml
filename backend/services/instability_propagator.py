"""
Cross-Cluster Instability Propagator
======================================
Implements problems.md §9:
  When an interruption event occurs in pool X:
    1. Update PoolPressure for that pool
    2. Recompute AZDelta for the AZ
    3. Re-evaluate other clusters sharing that pool
    4. Escalate only if systemic (multiple clusters impacted)

Prevents local noise from triggering global panic.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from backend.core.risk_engine import (
    calculate_bayesian_pool_pressure,
    compute_az_average_pressure,
    calculate_az_instability,
)

logger = logging.getLogger(__name__)

# ─── Redis keys ──────────────────────────────────────────────────
_KEY_POOL_PRESSURE   = "propagator:pool_pressure:{region}:{az}:{instance_type}"
_KEY_AZ_PRESSURE     = "propagator:az_pressure:{region}:{az}"
_KEY_POOL_EVENTS     = "propagator:events:{region}:{az}:{instance_type}"
_KEY_AFFECTED_COUNT  = "propagator:affected_count:{region}:{az}:{instance_type}"

# Systemic threshold: if >=3 clusters impacted → systemic (escalate)
SYSTEMIC_CLUSTER_THRESHOLD = 3

# TTL for propagator keys (2 hours)
_TTL = 7200


class InstabilityPropagator:
    """
    Propagates spot pool interruption events across clusters.
    """

    def __init__(self, redis_client, db_session=None):
        self.redis = redis_client
        self.db = db_session

    def record_interruption_event(
        self,
        region: str,
        az: str,
        instance_type: str,
        cluster_id: str,
        active_nodes: int = 5,
    ) -> dict:
        """
        Record a spot interruption event for a pool. Updates pool pressure
        and cross-cluster state.

        Returns propagation result dict.
        """
        event_key = _KEY_POOL_EVENTS.format(
            region=region, az=az, instance_type=instance_type
        )

        # Track affected clusters
        affected_key = _KEY_AFFECTED_COUNT.format(
            region=region, az=az, instance_type=instance_type
        )

        pipe = self.redis.pipeline()
        pipe.incr(event_key)
        pipe.expire(event_key, 1800)  # 30-min window for failures_30min
        pipe.sadd(affected_key, cluster_id)
        pipe.expire(affected_key, _TTL)
        results = pipe.execute()
        failures_30min = results[0]

        affected_clusters = self.redis.smembers(affected_key)
        affected_count = len(affected_clusters)

        # Recalculate pool pressure
        pool_pressure = calculate_bayesian_pool_pressure(
            failures_30min=failures_30min,
            active_nodes=active_nodes,
            minutes_since_last_event=0.0,
        )

        # Store updated pressure
        pressure_key = _KEY_POOL_PRESSURE.format(
            region=region, az=az, instance_type=instance_type
        )
        self.redis.set(pressure_key, str(pool_pressure), ex=_TTL)

        # Recompute AZ pressure
        az_pressure = self._recompute_az_pressure(region, az)

        # Determine if systemic
        is_systemic = affected_count >= SYSTEMIC_CLUSTER_THRESHOLD

        result = {
            "region": region,
            "az": az,
            "instance_type": instance_type,
            "failures_30min": failures_30min,
            "pool_pressure": round(pool_pressure, 4),
            "az_pressure": round(az_pressure, 4),
            "affected_clusters": list(
                c.decode() if isinstance(c, bytes) else c
                for c in affected_clusters
            ),
            "is_systemic": is_systemic,
            "recommended_action": "ESCALATE_ALL" if is_systemic else "UPDATE_LOCAL",
            "timestamp": datetime.utcnow().isoformat(),
        }

        if is_systemic:
            logger.warning(
                f"[InstabilityPropagator] SYSTEMIC event detected: "
                f"{instance_type} in {az}/{region} — {affected_count} clusters impacted"
            )
        else:
            logger.info(
                f"[InstabilityPropagator] Local interruption: "
                f"{instance_type} in {az}/{region} — cluster {cluster_id}"
            )

        return result

    def get_pool_pressure(
        self, region: str, az: str, instance_type: str
    ) -> float:
        """Retrieve stored pool pressure for a pool."""
        key = _KEY_POOL_PRESSURE.format(region=region, az=az, instance_type=instance_type)
        raw = self.redis.get(key)
        if raw is None:
            return 0.0
        return float(raw.decode() if isinstance(raw, bytes) else raw)

    def get_az_pressure(self, region: str, az: str) -> float:
        """Retrieve stored AZ average pressure."""
        key = _KEY_AZ_PRESSURE.format(region=region, az=az)
        raw = self.redis.get(key)
        if raw is None:
            return 0.0
        return float(raw.decode() if isinstance(raw, bytes) else raw)

    def get_az_delta(self, region: str, az: str, instance_type: str) -> float:
        """Compute AZ delta for a specific pool (for use in risk engine)."""
        pool_pressure = self.get_pool_pressure(region, az, instance_type)
        az_pressure = self.get_az_pressure(region, az)
        return calculate_az_instability(pool_pressure, az_pressure)

    def is_systemic_event(self, region: str, az: str, instance_type: str) -> bool:
        """Check if this pool has a systemic (multi-cluster) issue."""
        affected_key = _KEY_AFFECTED_COUNT.format(
            region=region, az=az, instance_type=instance_type
        )
        count = self.redis.scard(affected_key)
        return (count or 0) >= SYSTEMIC_CLUSTER_THRESHOLD

    def _recompute_az_pressure(self, region: str, az: str) -> float:
        """
        Scan all known pool pressures in this AZ and compute average.
        Stores result back in Redis.
        """
        pattern = _KEY_POOL_PRESSURE.format(region=region, az=az, instance_type="*")
        all_keys = self.redis.keys(pattern)
        pressures: List[float] = []
        for k in all_keys:
            raw = self.redis.get(k)
            if raw:
                try:
                    pressures.append(float(raw.decode() if isinstance(raw, bytes) else raw))
                except ValueError:
                    pass

        az_avg = compute_az_average_pressure(pressures)
        az_key = _KEY_AZ_PRESSURE.format(region=region, az=az)
        self.redis.set(az_key, str(az_avg), ex=_TTL)
        return az_avg

    def clear_pool_history(self, region: str, az: str, instance_type: str):
        """Reset state for a pool (e.g., after manual blacklist removal)."""
        for key_template in [_KEY_POOL_PRESSURE, _KEY_POOL_EVENTS, _KEY_AFFECTED_COUNT]:
            self.redis.delete(
                key_template.format(region=region, az=az, instance_type=instance_type)
            )
