"""
Circuit Breaker State Machine
==============================
Implements problems.md §8: NORMAL → CONSERVATIVE → HALT transitions.

State transitions:
  NORMAL      → CONSERVATIVE  : high rollback rate (>=2 in 1h)
  CONSERVATIVE → HALT         : continued failure (>=3 rollbacks in 1h from CONSERVATIVE)
  HALT        → CONSERVATIVE  : stable window (no failures for 30min)
  CONSERVATIVE → NORMAL       : decay window passes (2h in CONSERVATIVE, no failures)

Stored in Redis with per-cluster keys.
"""

from __future__ import annotations
import json
import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ─── Redis key templates ───────────────────────────────────────────
_KEY_STATE          = "cb:state:{cluster_id}"
_KEY_ROLLBACK_COUNT = "cb:rollbacks:{cluster_id}"
_KEY_LAST_FAILURE   = "cb:last_failure:{cluster_id}"
_KEY_STATE_ENTERED  = "cb:state_entered:{cluster_id}"

# ─── Thresholds ───────────────────────────────────────────────────
ROLLBACK_WINDOW_SECONDS      = 3600    # 1 hour window
NORMAL_TO_CONSERVATIVE_COUNT = 2       # >=2 rollbacks → CONSERVATIVE
CONSERVATIVE_TO_HALT_COUNT   = 3       # >=3 rollbacks while CONSERVATIVE → HALT
HALT_STABLE_SECONDS          = 1800    # 30 min no failures → CONSERVATIVE
CONSERVATIVE_DECAY_SECONDS   = 7200    # 2 h stable → NORMAL

STATES = ("NORMAL", "CONSERVATIVE", "HALT")


class CircuitBreaker:
    """
    Per-cluster circuit breaker backed by Redis.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    # ──────────────────────────────────────────────────────────────
    # State read
    # ──────────────────────────────────────────────────────────────

    def get_state(self, cluster_id: str) -> str:
        """Returns current state: NORMAL | CONSERVATIVE | HALT."""
        state = self.redis.get(_KEY_STATE.format(cluster_id=cluster_id))
        if state is None:
            return "NORMAL"
        return state.decode() if isinstance(state, bytes) else state

    def get_full_status(self, cluster_id: str) -> dict:
        """Return full circuit breaker status dict."""
        state = self.get_state(cluster_id)
        rollbacks = self._get_rollback_count(cluster_id)
        state_entered_raw = self.redis.get(_KEY_STATE_ENTERED.format(cluster_id=cluster_id))
        state_entered = None
        minutes_in_state = 0
        if state_entered_raw:
            try:
                state_entered = datetime.fromisoformat(
                    state_entered_raw.decode() if isinstance(state_entered_raw, bytes) else state_entered_raw
                )
                minutes_in_state = (datetime.utcnow() - state_entered).total_seconds() / 60
            except Exception:
                pass

        risk_multiplier = self._risk_multiplier(state, minutes_in_state)

        return {
            "state": state,
            "rollback_count_1h": rollbacks,
            "minutes_in_state": round(minutes_in_state, 1),
            "risk_multiplier": round(risk_multiplier, 3),
            "automation_allowed": state != "HALT",
            "state_entered_at": state_entered.isoformat() if state_entered else None,
        }

    # ──────────────────────────────────────────────────────────────
    # Event recording
    # ──────────────────────────────────────────────────────────────

    def record_rollback(
        self,
        cluster_id: str,
        is_emergency: bool = False,
        is_gate_rejection: bool = False,
    ) -> dict:
        """
        Record a rollback event and evaluate state transition.
        Returns new status dict.

        §11.2: Emergency actions (priority=10) and Mode 3 gate rejections
        do NOT increment the rollback counter — they are expected operational
        events, not signs of instability.
        """
        if is_emergency:
            logger.info(
                f"[CircuitBreaker] Cluster {cluster_id}: emergency rollback — "
                f"not incrementing counter"
            )
            return self.get_full_status(cluster_id)

        if is_gate_rejection:
            logger.info(
                f"[CircuitBreaker] Cluster {cluster_id}: gate rejection — "
                f"not incrementing counter"
            )
            return self.get_full_status(cluster_id)

        # Increment counter with 1h TTL
        key = _KEY_ROLLBACK_COUNT.format(cluster_id=cluster_id)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, ROLLBACK_WINDOW_SECONDS)
        results = pipe.execute()
        rollback_count = results[0]

        # Record last failure timestamp
        self.redis.set(
            _KEY_LAST_FAILURE.format(cluster_id=cluster_id),
            datetime.utcnow().isoformat(),
            ex=ROLLBACK_WINDOW_SECONDS,
        )

        # Evaluate transition
        current_state = self.get_state(cluster_id)
        new_state = self._evaluate_transition_on_failure(cluster_id, current_state, rollback_count)
        if new_state != current_state:
            self._set_state(cluster_id, new_state)
            logger.warning(
                f"[CircuitBreaker] Cluster {cluster_id}: {current_state} → {new_state} "
                f"(rollbacks={rollback_count})"
            )

        return self.get_full_status(cluster_id)

    def record_success(self, cluster_id: str) -> dict:
        """
        Record a successful execution. May trigger recovery transitions.
        Returns new status dict.
        """
        current_state = self.get_state(cluster_id)
        new_state = self._evaluate_transition_on_success(cluster_id, current_state)
        if new_state != current_state:
            self._set_state(cluster_id, new_state)
            logger.info(
                f"[CircuitBreaker] Cluster {cluster_id}: {current_state} → {new_state} (success recovery)"
            )
        return self.get_full_status(cluster_id)

    def check_and_auto_recover(self, cluster_id: str) -> dict:
        """
        Called periodically to evaluate time-based recovery transitions.
        Returns current status dict.
        """
        current_state = self.get_state(cluster_id)
        if current_state == "NORMAL":
            return self.get_full_status(cluster_id)

        new_state = self._evaluate_time_based_recovery(cluster_id, current_state)
        if new_state != current_state:
            self._set_state(cluster_id, new_state)
            logger.info(
                f"[CircuitBreaker] Cluster {cluster_id}: {current_state} → {new_state} (time recovery)"
            )

        return self.get_full_status(cluster_id)

    def get_risk_multiplier(self, cluster_id: str) -> float:
        """Return the current risk multiplier for a cluster."""
        state = self.get_state(cluster_id)
        minutes_in_state = self._get_minutes_in_state(cluster_id)
        return self._risk_multiplier(state, minutes_in_state)

    def reset(self, cluster_id: str, reason: str = "manual_reset") -> dict:
        """Admin: force reset to NORMAL."""
        self._set_state(cluster_id, "NORMAL")
        self.redis.delete(_KEY_ROLLBACK_COUNT.format(cluster_id=cluster_id))
        logger.warning(f"[CircuitBreaker] Cluster {cluster_id} manually reset: {reason}")
        return self.get_full_status(cluster_id)

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _get_rollback_count(self, cluster_id: str) -> int:
        raw = self.redis.get(_KEY_ROLLBACK_COUNT.format(cluster_id=cluster_id))
        if raw is None:
            return 0
        return int(raw)

    def _get_minutes_since_last_failure(self, cluster_id: str) -> Optional[float]:
        raw = self.redis.get(_KEY_LAST_FAILURE.format(cluster_id=cluster_id))
        if raw is None:
            return None
        try:
            ts = datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw)
            return (datetime.utcnow() - ts).total_seconds() / 60
        except Exception:
            return None

    def _get_minutes_in_state(self, cluster_id: str) -> float:
        raw = self.redis.get(_KEY_STATE_ENTERED.format(cluster_id=cluster_id))
        if raw is None:
            return 0.0
        try:
            ts = datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw)
            return (datetime.utcnow() - ts).total_seconds() / 60
        except Exception:
            return 0.0

    def _set_state(self, cluster_id: str, state: str):
        self.redis.set(_KEY_STATE.format(cluster_id=cluster_id), state, ex=86400)
        self.redis.set(
            _KEY_STATE_ENTERED.format(cluster_id=cluster_id),
            datetime.utcnow().isoformat(),
            ex=86400,
        )

    def _evaluate_transition_on_failure(
        self, cluster_id: str, current_state: str, rollback_count: int
    ) -> str:
        if current_state == "NORMAL" and rollback_count >= NORMAL_TO_CONSERVATIVE_COUNT:
            return "CONSERVATIVE"
        if current_state == "CONSERVATIVE" and rollback_count >= CONSERVATIVE_TO_HALT_COUNT:
            return "HALT"
        return current_state

    def _evaluate_transition_on_success(self, cluster_id: str, current_state: str) -> str:
        # Success doesn't immediately recover — requires stable time window
        return current_state

    def _evaluate_time_based_recovery(self, cluster_id: str, current_state: str) -> str:
        minutes_since_failure = self._get_minutes_since_last_failure(cluster_id)
        if minutes_since_failure is None:
            minutes_since_failure = 999.0  # No failures recorded → fully stable

        if current_state == "HALT":
            if minutes_since_failure >= HALT_STABLE_SECONDS / 60:
                return "CONSERVATIVE"
        elif current_state == "CONSERVATIVE":
            minutes_in_state = self._get_minutes_in_state(cluster_id)
            if (
                minutes_in_state >= CONSERVATIVE_DECAY_SECONDS / 60
                and minutes_since_failure >= HALT_STABLE_SECONDS / 60
            ):
                return "NORMAL"
        return current_state

    def _risk_multiplier(self, state: str, minutes_in_conservative: float) -> float:
        """
        Conservative risk multiplier with exponential decay (problems.md §3.3):
          RiskMultiplier = 1.3 × exp(-t / 120min)
        """
        if state == "HALT":
            return 2.0
        if state == "CONSERVATIVE":
            return 1.3 * math.exp(-minutes_in_conservative / 120.0)
        return 1.0
