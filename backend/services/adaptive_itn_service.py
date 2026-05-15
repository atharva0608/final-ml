"""
Adaptive Interruption Ledger Service.

Redis is the primary low-latency store for per-pool ledger data.
Postgres (adaptive_itn_ledger) serves as a durable backup written by the
hourly decay task.

C1: Ledger is now GLOBAL — keyed by pool (instance_type:az) only, no cluster_id.
An interruption seen by Customer A now raises the risk score for all customers
sharing that AWS pool.  Old per-cluster Redis keys (adaptive_itn:*) are
migrated to global_pool_ledger:* by scripts/migrate_global_pool_ledger.py.

Redis key schema:   global_pool_ledger:{instance_type}:{az}   (no TTL — permanent)
JSON payload:
  {
    "node_hours_observed":       float,
    "interruption_count":        int,     # total (legacy aggregate)
    "itn_warning_count":         int,     # C2: 2-min AWS ITN notices
    "actual_termination_count":  int,     # C2: nodes actually killed by AWS
    "rebalance_notice_count":    int,     # C2: AWS rebalance recommendations
    "peak_simultaneous_itn":     int,     # C2: max concurrent ITNs at one moment
    "raw_itn_score":             float,   # 0-1
    "confidence":                float,   # 0-1
    "last_interruption_ts":      str|null,  # ISO-8601 UTC
    "last_updated":              str        # ISO-8601 UTC
  }

Breadth is tracked via a separate Redis TTL-expiring set:
  pool_breadth_24h:{pool_key}   — SADD of cluster_ids seen in last 24 h (TTL 86 400 s)
  Use SCARD to read current breadth without storing a growing set in the main ledger.

Constants
---------
TAU                  = 720   h  — node-hours for confidence to reach ~63 %
                                  (full 1-σ trust ≈ 30 days of continuous running)
STABILITY_HALF_LIFE  = 168   h  — score halves ~weekly with no interruptions
MAX_RAW_ITN_SCORE    = 1.0

C3 — Severity-weighted spikes (replaces flat ITN_SCORE_BUMP = 0.30):
  SEVERITY_SPIKE["rebalance_notice"]   = 0.05
  SEVERITY_SPIKE["itn_warning"]        = 0.20
  SEVERITY_SPIKE["actual_termination"] = 0.40

C3 — Breadth multiplier (applied to the severity spike):
  1 cluster  → 1.0×
  2 clusters → 1.3×
  5 clusters → 1.6×
  10+        → 2.0×
"""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Tuning constants ────────────────────────────────────────────────────────
TAU = 720.0                  # node-hours for full confidence
STABILITY_HALF_LIFE = 168.0  # hours; score halves weekly with no interruptions
MAX_RAW_ITN_SCORE = 1.0

# ── C3: Severity-weighted spike constants ───────────────────────────────────
# Replaces the old flat ITN_SCORE_BUMP = 0.30.
# Each event type carries its own score increment before breadth scaling.
SEVERITY_SPIKE: dict = {
    "rebalance_notice":   0.05,   # AWS rebalance recommendation — low risk signal
    "itn_warning":        0.20,   # 2-min AWS termination notice — serious
    "actual_termination": 0.40,   # node actually killed by AWS — very serious
}

# ── C3: Breadth multiplier table ────────────────────────────────────────────
# Applied multiplicatively to the severity spike.
# Threshold: minimum number of distinct clusters affected in the last 24 h.
# Entry format: (threshold, multiplier).  List must be monotonically sorted.
BREADTH_MULTIPLIER_THRESHOLDS: list = [
    (1,  1.0),
    (2,  1.3),
    (5,  1.6),
    (10, 2.0),   # cap at 2.0
]


def get_breadth_multiplier(n_clusters: int) -> float:
    """Return the breadth multiplier for *n_clusters* distinct clusters affected."""
    for threshold, mult in reversed(BREADTH_MULTIPLIER_THRESHOLDS):
        if n_clusters >= threshold:
            return mult
    return 1.0


# ── C7: Severity-tiered cooldown TTLs ───────────────────────────────────────
# Replaces flat 6 h (21600 s) cooldown from B7.
# Lower-severity events (rebalance) lift sooner; actual terminations cool for 12 h.
COOLDOWN_TTL_SECONDS: dict = {
    "rebalance_notice":   2 * 3600,    # 2 hours — low severity
    "itn_warning":        6 * 3600,    # 6 hours — serious
    "actual_termination": 12 * 3600,   # 12 hours — very serious
}


def _redis_key(pool_key: str) -> str:
    """C1: Global ledger key — no cluster_id.  Replaces legacy adaptive_itn:{pool_key}."""
    return f"global_pool_ledger:{pool_key}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


class AdaptiveItnService:
    """
    All methods are @staticmethod so they can be called without instantiation.
    A redis_client must be passed explicitly; the service never holds state.
    """

    @staticmethod
    def get_ledger(pool_key: str, redis_client) -> dict:
        """
        Return the current ledger for *pool_key*.

        Falls back to Postgres when the Redis key is missing (e.g. after a
        Redis flush).  Returns a zeroed ledger if neither source has data.
        """
        raw = redis_client.get(_redis_key(pool_key))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass

        # Redis miss — try Postgres
        try:
            from backend.models.base import SessionLocal
            from backend.models.adaptive_itn_ledger import AdaptiveItnLedger
            db = SessionLocal()
            try:
                row = db.query(AdaptiveItnLedger).filter_by(pool_key=pool_key).first()
                if row:
                    ledger = {
                        "node_hours_observed": row.node_hours_observed,
                        "interruption_count": row.interruption_count,
                        # C2: severity breakdown — default to 0 for rows written before C2
                        "itn_warning_count": getattr(row, "itn_warning_count", None) or 0,
                        "actual_termination_count": getattr(row, "actual_termination_count", None) or 0,
                        "rebalance_notice_count": getattr(row, "rebalance_notice_count", None) or 0,
                        "peak_simultaneous_itn": getattr(row, "peak_simultaneous_itn", None) or 0,
                        "raw_itn_score": row.raw_itn_score,
                        "confidence": row.confidence,
                        "last_interruption_ts": _iso(row.last_interruption_ts)
                        if row.last_interruption_ts
                        else None,
                        "last_updated": _iso(row.last_updated),
                    }
                    # Backfill Redis
                    redis_client.set(_redis_key(pool_key), json.dumps(ledger))
                    return ledger
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[adaptive_itn] Postgres fallback failed for {pool_key}: {e}")

        # No data at all — return a clean zeroed ledger
        return {
            "node_hours_observed": 0.0,
            "interruption_count": 0,
            # C2: severity breakdown fields
            "itn_warning_count": 0,
            "actual_termination_count": 0,
            "rebalance_notice_count": 0,
            "peak_simultaneous_itn": 0,
            "raw_itn_score": 0.0,
            "confidence": 0.0,
            "last_interruption_ts": None,
            "last_updated": _iso(_now_utc()),
        }

    @staticmethod
    def record_interruption(
        pool_key: str,
        redis_client,
        event_type: str = "itn_warning",
        cluster_id: str = "",
        simultaneous_count: int = 1,
    ) -> None:
        """
        Record one interruption event for *pool_key*.

        C2/C3 changes
        -------------
        * event_type   one of "rebalance_notice", "itn_warning", "actual_termination"
                       (defaults to "itn_warning" for backward compat).
        * cluster_id   added to the pool_breadth_24h:{pool_key} Redis set (TTL 24h).
        * simultaneous_count  how many ITNs are happening right now; used to
                       update peak_simultaneous_itn.

        Score spike: SEVERITY_SPIKE[event_type] × get_breadth_multiplier(n_clusters),
        capped at MAX_RAW_ITN_SCORE.
        """
        ledger = AdaptiveItnService.get_ledger(pool_key, redis_client)

        # ── C2: increment per-type counter ──────────────────────────────────
        ledger["interruption_count"] = int(ledger.get("interruption_count", 0)) + 1
        _type_field_map = {
            "itn_warning":        "itn_warning_count",
            "actual_termination": "actual_termination_count",
            "rebalance_notice":   "rebalance_notice_count",
        }
        _count_field = _type_field_map.get(event_type, "itn_warning_count")
        ledger[_count_field] = int(ledger.get(_count_field, 0)) + 1

        # ── C2: update peak_simultaneous_itn ────────────────────────────────
        ledger["peak_simultaneous_itn"] = max(
            int(ledger.get("peak_simultaneous_itn", 0)),
            int(simultaneous_count),
        )

        # ── C2/C3: breadth — track distinct clusters in last 24 h ───────────
        _breadth_key = f"pool_breadth_24h:{pool_key}"
        n_clusters = 1
        try:
            if cluster_id:
                redis_client.sadd(_breadth_key, cluster_id)
                redis_client.expire(_breadth_key, 86400)   # 24 h TTL
            n_clusters = max(1, redis_client.scard(_breadth_key))
        except Exception as _be:
            logger.debug(f"[adaptive_itn] breadth key error for {pool_key}: {_be}")

        # ── C3: severity-weighted spike × breadth multiplier ────────────────
        base_spike = SEVERITY_SPIKE.get(event_type, SEVERITY_SPIKE["itn_warning"])
        scaled_spike = base_spike * get_breadth_multiplier(n_clusters)
        ledger["raw_itn_score"] = min(
            MAX_RAW_ITN_SCORE,
            float(ledger.get("raw_itn_score", 0.0)) + scaled_spike,
        )

        ledger["last_interruption_ts"] = _iso(_now_utc())
        ledger["last_updated"] = _iso(_now_utc())
        try:
            redis_client.set(_redis_key(pool_key), json.dumps(ledger))
        except Exception as e:
            logger.warning(f"[adaptive_itn] Failed to write interruption for {pool_key}: {e}")

        # Short-term cooldown: skip this pool in selection until the per-severity
        # TTL expires, giving the adaptive score time to decay (C7).
        try:
            redis_client.setex(
                f"itn_cooldown:{pool_key}",
                COOLDOWN_TTL_SECONDS.get(event_type, 21600),
                event_type,
            )
        except Exception as _ce:
            logger.warning(f"[adaptive_itn] Failed to set cooldown for {pool_key}: {_ce}")

    @staticmethod
    def record_global_interruption(
        pool_key: str,
        cluster_id: str,
        event_type: str,
        initiated_by: str,
        redis_client,
        simultaneous_count: int = 1,
    ) -> None:
        """
        C4 — Canonical ingestion point for all interruption signals.

        Source filter: only events with initiated_by="aws" touch the global
        ledger.  Rebalancer-initiated drains and Karpenter consolidations are
        silently ignored so they cannot inflate the AWS risk signal.

        Args:
            pool_key         "instance_type:az", e.g. "m5.large:us-east-1a"
            cluster_id       Cluster that observed this event (for breadth tracking)
            event_type       "rebalance_notice" | "itn_warning" | "actual_termination"
            initiated_by     "aws" | "rebalancer" | "karpenter_consolidation"
            redis_client     Active Redis client
            simultaneous_count  For peak_simultaneous_itn; pass Redis SCARD result
                             of a concurrent-ITN key when available.
        """
        if initiated_by != "aws":
            logger.debug(
                f"[adaptive_itn] Ignoring non-AWS interruption "
                f"(initiated_by={initiated_by!r}) for {pool_key}"
            )
            return

        AdaptiveItnService.record_interruption(
            pool_key=pool_key,
            redis_client=redis_client,
            event_type=event_type,
            cluster_id=cluster_id,
            simultaneous_count=simultaneous_count,
        )

    @staticmethod
    def get_adaptive_risk(pool_key: str, redis_client) -> Tuple[float, float]:
        """
        Return (adaptive_risk, confidence) for *pool_key*.

        adaptive_risk — raw_itn_score in [0, 1] (already decayed over time)
        confidence    — 1 - exp(-node_hours_observed / TAU) in [0, 1]

        Both are 0.0 when no ledger data exists.
        """
        ledger = AdaptiveItnService.get_ledger(pool_key, redis_client)
        raw_score = float(ledger.get("raw_itn_score", 0.0))
        confidence = float(ledger.get("confidence", 0.0))
        return raw_score, confidence

    @staticmethod
    def get_global_pool_context(pool_key: str, redis_client) -> dict:
        """
        C9/C10: Return the full global-ledger context needed for risk blending and UI.

        Keys are read from global_pool_ledger:{pool_key} (C1 — no cluster_id).

        Returns:
            adaptive_risk        — raw_itn_score in [0, 1]
            adaptive_confidence  — 1 - exp(-node_hours / TAU)
            global_itn_breadth   — distinct clusters that triggered any event in the
                                   last 24 h (SCARD of pool_breadth_24h:{pool_key})
            global_itn_severity  — worst event type recorded in the ledger:
                                   "actual_termination" > "itn_warning" >
                                   "rebalance_notice" > None (no history)
        """
        ledger = AdaptiveItnService.get_ledger(pool_key, redis_client)
        raw_score = float(ledger.get("raw_itn_score", 0.0))
        confidence = float(ledger.get("confidence", 0.0))

        # Breadth from the separate 24 h TTL-expiring set
        breadth = 0
        try:
            breadth = max(0, int(redis_client.scard(f"pool_breadth_24h:{pool_key}")))
        except Exception:
            pass

        # Worst severity derived from per-type counters (C2 fields)
        severity: Optional[str] = None
        if int(ledger.get("actual_termination_count", 0)) > 0:
            severity = "actual_termination"
        elif int(ledger.get("itn_warning_count", 0)) > 0:
            severity = "itn_warning"
        elif int(ledger.get("rebalance_notice_count", 0)) > 0:
            severity = "rebalance_notice"

        return {
            "adaptive_risk":       raw_score,
            "adaptive_confidence": confidence,
            "global_itn_breadth":  breadth,
            "global_itn_severity": severity,
        }

    @staticmethod
    def apply_hourly_decay(pool_key: str, redis_client, elapsed_hours: float = 1.0) -> dict:
        """
        Advance the ledger by *elapsed_hours*:

        1. node_hours_observed += elapsed_hours
        2. confidence = 1 - exp(-node_hours_observed / TAU)
        3. If last_interruption_ts is set:
               hours_since_itn = elapsed time since last interruption
               raw_itn_score  *= exp(-hours_since_itn / STABILITY_HALF_LIFE)
           (Uses actual wall-clock time, not just elapsed_hours, so that
            multiple decay runs converge correctly.)
        4. last_updated = now

        Returns the updated ledger dict (also written back to Redis).
        """
        ledger = AdaptiveItnService.get_ledger(pool_key, redis_client)
        now = _now_utc()

        # C6: Harvest the INCRBYFLOAT accumulator written by accumulate_global_node_hours.
        # GETDEL atomically reads and removes the key so hours are counted exactly once
        # even if the decay task fires slightly late.  Falls back to the elapsed_hours
        # parameter (1.0 h) if the accumulator key is absent (new pools, test environments).
        _accum_key = f"global_pool_ledger:{pool_key}:node_hours"
        try:
            _accum_raw = redis_client.getdel(_accum_key)   # Redis 6.2+
            if _accum_raw:
                elapsed_hours = float(_accum_raw)
        except Exception:
            pass  # fall back to the caller-supplied elapsed_hours

        # 1. Increment node-hours
        node_hours = float(ledger.get("node_hours_observed", 0.0)) + elapsed_hours
        ledger["node_hours_observed"] = node_hours

        # 2. Recompute confidence
        ledger["confidence"] = 1.0 - math.exp(-node_hours / TAU)

        # 3. Decay raw interruption score
        last_itn_ts = _parse_iso(ledger.get("last_interruption_ts"))
        if last_itn_ts:
            hours_since_itn = (now - last_itn_ts).total_seconds() / 3600.0
            decay_factor = math.exp(-hours_since_itn / STABILITY_HALF_LIFE)
            ledger["raw_itn_score"] = float(ledger.get("raw_itn_score", 0.0)) * decay_factor

        ledger["last_updated"] = _iso(now)

        try:
            redis_client.set(_redis_key(pool_key), json.dumps(ledger))
        except Exception as e:
            logger.warning(f"[adaptive_itn] Failed to write decay for {pool_key}: {e}")

        return ledger

    @staticmethod
    def flush_to_postgres(pool_key: str, ledger: dict, db=None) -> None:
        """
        Upsert *ledger* data into the Postgres backup table.
        If *db* is None a new session is created and closed internally.
        """
        close_db = False
        if db is None:
            from backend.models.base import SessionLocal
            db = SessionLocal()
            close_db = True
        try:
            from backend.models.adaptive_itn_ledger import AdaptiveItnLedger
            row = db.query(AdaptiveItnLedger).filter_by(pool_key=pool_key).first()
            if row is None:
                row = AdaptiveItnLedger(pool_key=pool_key)
                db.add(row)
            row.node_hours_observed = float(ledger.get("node_hours_observed", 0.0))
            row.interruption_count = int(ledger.get("interruption_count", 0))
            # C2: severity breakdown — only written if the column already exists
            # (guard with hasattr so the same code works before the migration runs)
            if hasattr(row, "itn_warning_count"):
                row.itn_warning_count = int(ledger.get("itn_warning_count", 0))
            if hasattr(row, "actual_termination_count"):
                row.actual_termination_count = int(ledger.get("actual_termination_count", 0))
            if hasattr(row, "rebalance_notice_count"):
                row.rebalance_notice_count = int(ledger.get("rebalance_notice_count", 0))
            if hasattr(row, "peak_simultaneous_itn"):
                row.peak_simultaneous_itn = int(ledger.get("peak_simultaneous_itn", 0))
            row.raw_itn_score = float(ledger.get("raw_itn_score", 0.0))
            row.confidence = float(ledger.get("confidence", 0.0))
            last_itn = _parse_iso(ledger.get("last_interruption_ts"))
            row.last_interruption_ts = last_itn
            db.commit()
        except Exception as e:
            logger.warning(f"[adaptive_itn] Postgres flush failed for {pool_key}: {e}")
            if db:
                db.rollback()
        finally:
            if close_db and db:
                db.close()
