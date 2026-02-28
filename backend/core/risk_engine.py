"""
Risk Engine — Deterministic Spot Risk Computation
==================================================

Implements the full risk model from problems.md:
  - Bayesian Pool Pressure (time-decayed)
  - AZ-Level Instability (delta-corrected to avoid double-counting)
  - Normalized Price Volatility (EMA-based)
  - Base Risk & Final Risk composition

All functions are pure / stateless — pass in pre-fetched data,
get back a float.  The calling service is responsible for Redis I/O.
"""

from __future__ import annotations

import math
import statistics
from typing import List, Optional


# ─────────────────────────────────────────────────────────────
# 1. Bayesian Pool Pressure (section 3.1 of problems.md)
# ─────────────────────────────────────────────────────────────

# Laplace smoothing constant – prevents division-by-zero on new pools
_K_LAPLACE: float = 4.0

# Half-life of pool pressure in minutes
_T_POOL_MINUTES: float = 60.0


def calculate_bayesian_pool_pressure(
    failures_30min: int,
    active_nodes: int,
    minutes_since_last_event: float = 0.0,
) -> float:
    """
    Bayesian pool pressure with exponential time decay.

    Formula (problems.md §3.1):
        Pressure_raw = (failures + k) / (active_nodes + k)
        PoolPressure  = Pressure_raw × exp(-Δt / T_pool)

    Args:
        failures_30min: Interruption / capacity failures in the last 30 min.
        active_nodes:   Current live nodes in this pool.
        minutes_since_last_event: Minutes elapsed since last failure event.
                                  0 = right now, 60 = one T_pool ago.

    Returns:
        Clamped float in [0.0, 1.0].
    """
    pressure_raw = (failures_30min + _K_LAPLACE) / (active_nodes + _K_LAPLACE)
    decay = math.exp(-minutes_since_last_event / _T_POOL_MINUTES)
    return float(min(max(pressure_raw * decay, 0.0), 1.0))


# ─────────────────────────────────────────────────────────────
# 2. AZ-Level Instability (section 3.2)
# ─────────────────────────────────────────────────────────────


def calculate_az_instability(
    pool_pressure: float,
    az_average_pressure: float,
) -> float:
    """
    AZ-level delta corrected to prevent double-counting with pool pressure.

    Formula (problems.md §3.2):
        AZPressure_raw = average(PoolPressure in AZ)
        AZDelta        = max(AZPressure_raw - PoolPressure, 0)

    Args:
        pool_pressure:      This pool's pressure (already computed).
        az_average_pressure: Mean pool pressure across ALL pools in the same AZ.

    Returns:
        Float in [0.0, 1.0].
    """
    az_delta = max(az_average_pressure - pool_pressure, 0.0)
    return float(min(az_delta, 1.0))


def compute_az_average_pressure(pool_pressures_in_az: List[float]) -> float:
    """
    Helper: average pool pressure for all pools in an AZ.
    Returns 0.0 on empty list.
    """
    if not pool_pressures_in_az:
        return 0.0
    return float(sum(pool_pressures_in_az) / len(pool_pressures_in_az))


# ─────────────────────────────────────────────────────────────
# 3. Price Volatility (section 3.3)
# ─────────────────────────────────────────────────────────────


def calculate_normalized_volatility(
    price_samples_60min: List[float],
    ema_30_price: Optional[float] = None,
) -> float:
    """
    Normalized spot-price volatility over the last 60 minutes.

    Formula (problems.md §3.3):
        MeanPrice          = EMA_30  (or simple mean if not available)
        StdDev             = std(prices_last_60min)
        NormalizedVolatility = StdDev / MeanPrice

    Args:
        price_samples_60min: List of spot prices sampled over the last 60 min.
        ema_30_price:        30-period EMA price (preferred).  Falls back to
                             simple mean of the provided samples.

    Returns:
        Clamped float in [0.0, 1.0].  (1.0 = 100 % std/mean)
    """
    if len(price_samples_60min) < 2:
        return 0.0

    mean_price = ema_30_price if ema_30_price and ema_30_price > 0 else statistics.mean(price_samples_60min)
    if mean_price <= 0:
        return 0.0

    std_dev = statistics.stdev(price_samples_60min)
    normalized = std_dev / mean_price
    return float(min(max(normalized, 0.0), 1.0))


# ─────────────────────────────────────────────────────────────
# 4. Base Risk (section 3.4)
# ─────────────────────────────────────────────────────────────

# Weights per problems.md §3.4
_W_ADJUSTED_ML = 0.35
_W_VOLATILITY = 0.10

# Blending weight for Spot Advisor risk adjustment
_ALPHA_ADVISOR = 0.3


def compute_base_risk(
    ml_risk: float,
    advisor_risk: float,
    normalized_volatility: float,
) -> float:
    """
    Compute base risk from ML model + Spot Advisor + price volatility.

    Formula (problems.md §3.4):
        AdjustedML = ML_Risk × (1 + AdvisorRisk × α)
        BaseRisk   = (AdjustedML × 0.35) + (NormalizedVolatility × 0.10)

    Args:
        ml_risk:               ML classifier output [0, 1].
        advisor_risk:          Spot Advisor interruption frequency [0, 1].
        normalized_volatility: From calculate_normalized_volatility().

    Returns:
        Float in [0.0, 1.0].
    """
    adjusted_ml = ml_risk * (1 + advisor_risk * _ALPHA_ADVISOR)
    adjusted_ml = min(adjusted_ml, 1.0)

    base_risk = (adjusted_ml * _W_ADJUSTED_ML) + (normalized_volatility * _W_VOLATILITY)
    return float(min(max(base_risk, 0.0), 1.0))


# ─────────────────────────────────────────────────────────────
# 5. Final Risk (section 3.5)
# ─────────────────────────────────────────────────────────────

# Weights per problems.md §3.5
_W_POOL_PRESSURE = 0.25
_W_AZ_DELTA = 0.15
_W_CLUSTER_INSTABILITY = 0.15

# Exponential decay time-constant for conservative mode (seconds)
_TAU_CONSERVATIVE_SECONDS: float = 7200.0  # 120 minutes


def compute_cluster_instability_boost(
    instability_mode: str,
    minutes_in_conservative: float = 0.0,
) -> float:
    """
    Cluster instability boost applied when cluster is in CONSERVATIVE mode.
    Legacy non-Redis version — kept for backward compatibility.

    Formula (problems.md §3.3 decay):
        RiskMultiplier = 1.3 × exp(-t / τ)

    In HALT mode the boost is capped at 1.0 (maximum possible contribution).
    In NORMAL mode boost is 0.
    """
    if instability_mode == "HALT":
        return 1.0
    if instability_mode == "CONSERVATIVE":
        boost = 1.3 * math.exp(-minutes_in_conservative / _TAU_CONSERVATIVE_MINUTES)
        return float(min(max(boost - 1.0, 0.0), 1.0))  # subtract baseline 1.0
    return 0.0


# ── Task 4.2: Persistent Cluster State Machine via Redis ─────

def get_cluster_instability_boost(cluster_id: str, redis_client) -> float:
    """
    Redis-backed instability boost. Reads persistent cluster state from Redis hash.
    Decay is computed from real entered_at timestamp, surviving worker restarts.
    
    Returns a boost value in [0.0, 1.3].
    """
    import time

    state_key = f"spot:cluster_state:{cluster_id}"
    state = redis_client.hgetall(state_key)

    if not state:
        # First time this cluster has been seen — initialize
        redis_client.hset(state_key, mapping={
            "state": "NORMAL",
            "entered_at": str(time.time()),
            "rollback_count": "0",
            "instability_score": "0.0",
            "last_transition_reason": "initialized",
        })
        return 0.0

    current_state = state.get(b"state", b"NORMAL").decode()

    if current_state == "CONSERVATIVE":
        entered_at = float(state.get(b"entered_at", b"0").decode())
        t = time.time() - entered_at
        tau = _TAU_CONSERVATIVE_SECONDS  # 7200 seconds (120 minutes)
        return 1.3 * math.exp(-t / tau)

    elif current_state == "HALT":
        return 1.0

    else:  # NORMAL
        return 0.0


def transition_cluster_state(cluster_id: str, new_state: str, reason: str, redis_client):
    """
    Persist a cluster state transition to Redis.
    States: NORMAL, CONSERVATIVE, HALT
    
    Do NOT set a TTL on this key — permanent for cluster's lifetime.
    """
    import time
    state_key = f"spot:cluster_state:{cluster_id}"
    redis_client.hset(state_key, mapping={
        "state": new_state,
        "entered_at": str(time.time()),
        "last_transition_reason": reason,
    })
    # Increment rollback_count if transitioning to CONSERVATIVE or HALT
    if new_state in ("CONSERVATIVE", "HALT"):
        redis_client.hincrby(state_key, "rollback_count", 1)


def compute_final_risk(
    base_risk: float,
    pool_pressure: float,
    az_delta: float,
    cluster_instability_boost: float,
) -> float:
    """
    Final composite risk score.

    Formula (problems.md §3.5):
        FinalRisk = BaseRisk
                    + (PoolPressure         × 0.25)
                    + (AZDelta              × 0.15)
                    + (ClusterInstability   × 0.15)

    Returns:
        Clamped float in [0.0, 1.0].
    """
    final = (
        base_risk
        + pool_pressure * _W_POOL_PRESSURE
        + az_delta * _W_AZ_DELTA
        + cluster_instability_boost * _W_CLUSTER_INSTABILITY
    )
    return float(min(max(final, 0.0), 1.0))


# ─────────────────────────────────────────────────────────────
# 6. Convenience: full pipeline for a single pool
# ─────────────────────────────────────────────────────────────


def compute_pool_risk(
    ml_risk: float,
    advisor_risk: float,
    failures_30min: int,
    active_nodes: int,
    minutes_since_last_event: float,
    az_pool_pressures: List[float],
    price_samples_60min: List[float],
    ema_30_price: Optional[float],
    instability_mode: str = "NORMAL",
    minutes_in_conservative: float = 0.0,
) -> dict:
    """
    Full risk pipeline for a single pool.  Returns an explainable dict so
    every component can be logged for observability/replayability.

    Returns:
        {
            pool_pressure, az_delta, normalized_volatility,
            base_risk, cluster_boost, final_risk
        }
    """
    pool_pressure = calculate_bayesian_pool_pressure(
        failures_30min, active_nodes, minutes_since_last_event
    )

    az_avg = compute_az_average_pressure(az_pool_pressures)
    az_delta = calculate_az_instability(pool_pressure, az_avg)

    normalized_vol = calculate_normalized_volatility(price_samples_60min, ema_30_price)

    base_risk = compute_base_risk(ml_risk, advisor_risk, normalized_vol)

    cluster_boost = compute_cluster_instability_boost(instability_mode, minutes_in_conservative)

    final_risk = compute_final_risk(base_risk, pool_pressure, az_delta, cluster_boost)

    return {
        "pool_pressure": round(pool_pressure, 4),
        "az_delta": round(az_delta, 4),
        "normalized_volatility": round(normalized_vol, 4),
        "base_risk": round(base_risk, 4),
        "cluster_instability_boost": round(cluster_boost, 4),
        "final_risk": round(final_risk, 4),
    }
