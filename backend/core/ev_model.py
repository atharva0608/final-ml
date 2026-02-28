"""
Economic Expected Value Model — Full EV Computation
====================================================
Implements problems.md §4: Full economic model beyond simple savings × (1-risk).
  - Risk Horizon Alignment (§4.1)
  - Expected Interruption Cost (§4.2)
  - Capacity Failure Risk (§4.3)
  - Migration Penalty (§4.4)
  - Final EV with decision rule (§4.5)
"""

from __future__ import annotations
from typing import Optional


# ── Task 3.1: Dynamic Capacity Failure Probability ───────────

def get_dynamic_capacity_failure_probability(redis_client, pool_id: str, region: str) -> float:
    """
    Compute real observed DryRun failure rate for a pool.
    Falls back to 0.05 if no data yet.
    
    Replaces hardcoded capacity_failure_probability of 0.05 with live signal
    from actual DryRun capacity checks stored in Redis.
    """
    failures_key = f"spot:dryrun_failures_24h:{pool_id}"
    count_key = f"spot:dryrun_count:{region}"

    failures = redis_client.get(failures_key)
    attempts = redis_client.get(count_key)

    failures = int(failures) if failures else 0
    attempts = int(attempts) if attempts else 1  # avoid division by zero

    if attempts == 0:
        return 0.05  # default fallback

    probability = failures / attempts
    return min(probability, 0.50)  # cap at 50% — never assume total failure


# ──────────────────────────────────────────────────────────────────
# 4.1  Risk Horizon Alignment
# ──────────────────────────────────────────────────────────────────

def compute_effective_exposure_hours(
    risk_horizon_hours: float,
    recovery_time_hours: float,
) -> float:
    """
    EffectiveExposureHours = min(RiskHorizonHours, RecoveryTimeHours)
    Caps the cost window to actual recovery capability.
    """
    return min(risk_horizon_hours, recovery_time_hours)


# ──────────────────────────────────────────────────────────────────
# 4.2  Expected Interruption Cost
# ──────────────────────────────────────────────────────────────────

def compute_expected_interruption_cost(
    final_risk: float,
    downtime_cost_per_hour: float,
    effective_exposure_hours: float,
) -> float:
    """
    ExpectedInterruptionCost = FinalRisk × DowntimeCostPerHour × EffectiveExposureHours
    """
    return final_risk * downtime_cost_per_hour * effective_exposure_hours


# ──────────────────────────────────────────────────────────────────
# 4.3  Capacity Failure Risk
# ──────────────────────────────────────────────────────────────────

def compute_capacity_failure_risk(
    capacity_failure_probability: float,
    retry_cost: float,
) -> float:
    """
    CapacityFailureRisk = CapacityFailureProbability × RetryCost
    """
    return capacity_failure_probability * retry_cost


# ──────────────────────────────────────────────────────────────────
# 4.4  Migration Penalty
# ──────────────────────────────────────────────────────────────────

def compute_migration_penalty(
    drain_time_cost: float,
    warmup_cost: float,
    control_plane_cost: float,
) -> float:
    """
    MigrationPenalty = DrainTimeCost + WarmupCost + ControlPlaneCost
    """
    return drain_time_cost + warmup_cost + control_plane_cost


# ──────────────────────────────────────────────────────────────────
# 4.5  Final EV
# ──────────────────────────────────────────────────────────────────

def compute_full_ev(
    savings: float,
    expected_interruption_cost: float,
    migration_penalty: float,
    capacity_failure_risk: float,
    normalized_volatility: float,
    volatility_cost_multiplier: float = 1.0,
) -> float:
    """
    EV = Savings
         - ExpectedInterruptionCost
         - MigrationPenalty
         - CapacityFailureRisk
         - (NormalizedVolatility × VolatilityCostMultiplier)

    Decision rule: EV > 0 AND guardrails pass → candidate eligible.
    """
    ev = (
        savings
        - expected_interruption_cost
        - migration_penalty
        - capacity_failure_risk
        - (normalized_volatility * volatility_cost_multiplier)
    )
    return ev


# ──────────────────────────────────────────────────────────────────
# Convenience: Full pipeline
# ──────────────────────────────────────────────────────────────────

def evaluate_candidate_ev(
    savings: float,
    final_risk: float,
    normalized_volatility: float,
    # Risk horizon params
    risk_horizon_hours: float = 2.0,
    recovery_time_hours: float = 0.5,
    # Cost params
    downtime_cost_per_hour: float = 100.0,
    retry_cost: float = 10.0,
    capacity_failure_probability: float = 0.05,
    drain_time_cost: float = 2.0,
    warmup_cost: float = 1.0,
    control_plane_cost: float = 0.5,
    volatility_cost_multiplier: float = 5.0,
) -> dict:
    """
    Full EV pipeline — returns explainable breakdown dict.

    Returns:
        {ev, savings, interruption_cost, migration_penalty,
         capacity_failure_risk, volatility_cost, is_eligible}
    """
    exposure_hours = compute_effective_exposure_hours(risk_horizon_hours, recovery_time_hours)
    interruption_cost = compute_expected_interruption_cost(final_risk, downtime_cost_per_hour, exposure_hours)
    capacity_risk = compute_capacity_failure_risk(capacity_failure_probability, retry_cost)
    migration = compute_migration_penalty(drain_time_cost, warmup_cost, control_plane_cost)
    volatility_cost = normalized_volatility * volatility_cost_multiplier

    ev = compute_full_ev(
        savings=savings,
        expected_interruption_cost=interruption_cost,
        migration_penalty=migration,
        capacity_failure_risk=capacity_risk,
        normalized_volatility=normalized_volatility,
        volatility_cost_multiplier=volatility_cost_multiplier,
    )

    return {
        "ev": round(ev, 4),
        "savings": round(savings, 4),
        "interruption_cost": round(interruption_cost, 4),
        "migration_penalty": round(migration, 4),
        "capacity_failure_risk": round(capacity_risk, 4),
        "volatility_cost": round(volatility_cost, 4),
        "effective_exposure_hours": round(exposure_hours, 2),
        "is_eligible": ev > 0,
    }
