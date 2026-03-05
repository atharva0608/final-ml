"""
Step 0b: Full Economic Expected Value Model
===========================================
Source: backend/core/ev_model.py

PURPOSE
-------
Extends the simple EV formula (01_scoring.py) with full economic modeling.
Used for EXECUTION DECISIONS only — not for pool ranking/sorting.

WHY MORE COMPLEX THAN SIMPLE EV?
---------------------------------
The simple formula (savings × (1 - risk)) ignores real economic factors:
  1. Interruption doesn't happen instantly — there's a risk HORIZON
  2. Interruptions cost money in DOWNTIME ($100/hr default per node)
  3. EC2 may not have capacity when you try to launch a replacement (CAPACITY FAILURE)
  4. Moving a node causes MIGRATION overhead (drain time, warmup, API calls)
  5. Price VOLATILITY means today's cheap pool may spike tomorrow

This model accounts for all five factors to make accurate go/no-go decisions.

PIPELINE (4 sub-components)
----------------------------

  §4.1 Risk Horizon Alignment
       EffectiveExposureHours = min(RiskHorizon, RecoveryTime)
       → Caps downtime window to what we can actually recover in

  §4.2 Expected Interruption Cost
       InterruptionCost = FinalRisk × DowntimeCost/hr × ExposureHours
       → How much an interruption would cost in expectation

  §4.3 Capacity Failure Risk
       CapacityRisk = FailureProbability × RetryCost
       → Risk that EC2 won't have capacity when we need to launch replacement
       → Probability is DYNAMIC: read from Redis (live DryRun failure rate)

  §4.4 Migration Penalty
       MigrationPenalty = DrainCost + WarmupCost + ControlPlaneCost
       → One-time cost incurred when moving a node ($3.50 default total)

  §4.5 Final EV
       EV = Savings - InterruptionCost - MigrationPenalty
                    - CapacityRisk - VolatilityCost
       Decision Rule: EV > 0 AND guardrails pass → pool is eligible

DEFAULTS (tuned to real AWS economics)
---------------------------------------
  downtime_cost_per_hour:   $100/hr per affected node (SLA penalty estimate)
  risk_horizon_hours:       2h (Karpenter SLA window)
  recovery_time_hours:      0.5h (30 min to provision replacement)
  retry_cost:               $10 (on-demand instance cost during retry)
  drain_time_cost:          $2 (15 min drain at $8/hr OD rate)
  warmup_cost:              $1 (JVM warmup, cache cold start)
  control_plane_cost:       $0.50 (K8s API calls, state sync)
  volatility_cost_multiplier: $5 × normalized_volatility
"""

from __future__ import annotations
from typing import Optional


# ---------------------------------------------------------------------------
# §4.1  Risk Horizon Alignment
# ---------------------------------------------------------------------------

def compute_effective_exposure_hours(
    risk_horizon_hours: float,
    recovery_time_hours: float,
) -> float:
    """
    Cap the downtime cost window to actual recovery capability.

    Example: If Karpenter can provision a replacement in 30 min,
    even a 2h risk horizon only costs 0.5h of downtime.

    Args:
        risk_horizon_hours:   How far ahead we evaluate risk (default: 2h)
        recovery_time_hours:  How long it takes to recover from interruption (default: 0.5h)

    Returns:
        Effective exposure in hours (the smaller of the two)
    """
    return min(risk_horizon_hours, recovery_time_hours)


# ---------------------------------------------------------------------------
# §4.2  Expected Interruption Cost
# ---------------------------------------------------------------------------

def compute_expected_interruption_cost(
    final_risk: float,
    downtime_cost_per_hour: float,
    effective_exposure_hours: float,
) -> float:
    """
    Expected dollar cost of a spot interruption.

    Formula: FinalRisk × DowntimeCostPerHour × EffectiveExposureHours

    Example:
        Risk=10%, Downtime=$100/hr, Exposure=0.5h
        → Cost = 0.10 × 100 × 0.5 = $5

    Args:
        final_risk:               Interpolation probability from XGBoost (0.0–1.0)
        downtime_cost_per_hour:   SLA penalty per affected node per hour ($)
        effective_exposure_hours: Output of compute_effective_exposure_hours()

    Returns:
        Expected interruption cost in dollars
    """
    return final_risk * downtime_cost_per_hour * effective_exposure_hours


# ---------------------------------------------------------------------------
# §4.3  Capacity Failure Risk
# ---------------------------------------------------------------------------

def get_dynamic_capacity_failure_probability(
    redis_client, pool_id: str, region: str
) -> float:
    """
    Get real observed DryRun failure rate for a spot pool from Redis.

    The agent performs EC2 DryRun before each substitute deployment.
    Failure rates are stored in Redis and read here for live signal.
    Falls back to 5% default if no data exists.

    Redis Keys:
        spot:dryrun_failures_24h:{pool_id}  — rolling 24h failure count
        spot:dryrun_count:{region}           — total attempts in region

    Args:
        redis_client:  Redis connection
        pool_id:       "{instance_type}:{az}" e.g. "m5.large:us-east-1a"
        region:        AWS region e.g. "us-east-1"

    Returns:
        Failure probability in [0.0, 0.5] (capped at 50%)
    """
    failures_key = f"spot:dryrun_failures_24h:{pool_id}"
    count_key = f"spot:dryrun_count:{region}"

    failures = redis_client.get(failures_key)
    attempts = redis_client.get(count_key)

    failures = int(failures) if failures else 0
    attempts = int(attempts) if attempts else 1  # avoid division by zero

    probability = failures / attempts
    return min(probability, 0.50)  # never assume total failure


def compute_capacity_failure_risk(
    capacity_failure_probability: float,
    retry_cost: float,
) -> float:
    """
    Cost risk from EC2 capacity unavailability.

    If EC2 doesn't have capacity for your instance type + AZ combination,
    the replacement provisioning fails and you must retry (on-demand fallback).
    This models the expected cost of that scenario.

    Formula: CapacityFailureProbability × RetryCost

    Args:
        capacity_failure_probability: From get_dynamic_capacity_failure_probability()
        retry_cost:                   Cost of on-demand fallback provisioning ($)

    Returns:
        Expected capacity failure cost in dollars
    """
    return capacity_failure_probability * retry_cost


# ---------------------------------------------------------------------------
# §4.4  Migration Penalty
# ---------------------------------------------------------------------------

def compute_migration_penalty(
    drain_time_cost: float,
    warmup_cost: float,
    control_plane_cost: float,
) -> float:
    """
    One-time cost of moving a node to a different spot pool.

    Components:
      drain_time_cost:    Cost during graceful drain period (30s–5min)
                          Example: $2 = 15min × $8/hr on-demand rate
      warmup_cost:        Application warmup overhead (JVM, caches)
                          Example: $1 for typical stateless service
      control_plane_cost: K8s API overhead (pod reschedule, DNS, LB update)
                          Example: $0.50 flat rate

    Formula: DrainTimeCost + WarmupCost + ControlPlaneCost

    Returns:
        Total migration penalty in dollars
    """
    return drain_time_cost + warmup_cost + control_plane_cost


# ---------------------------------------------------------------------------
# §4.5  Final EV + Decision Rule
# ---------------------------------------------------------------------------

def compute_full_ev(
    savings: float,
    expected_interruption_cost: float,
    migration_penalty: float,
    capacity_failure_risk: float,
    normalized_volatility: float,
    volatility_cost_multiplier: float = 1.0,
) -> float:
    """
    Full economic EV for a candidate spot pool.

    Formula:
        EV = Savings
             - ExpectedInterruptionCost
             - MigrationPenalty
             - CapacityFailureRisk
             - (NormalizedVolatility × VolatilityCostMultiplier)

    Decision Rule:
        EV > 0 → candidate is economically eligible
        EV ≤ 0 → candidate costs more than it saves (reject)

    Args:
        savings:                    Expected hourly savings vs on-demand ($)
        expected_interruption_cost: From compute_expected_interruption_cost()
        migration_penalty:          From compute_migration_penalty()
        capacity_failure_risk:      From compute_capacity_failure_risk()
        normalized_volatility:      Price volatility score 0.0–1.0
        volatility_cost_multiplier: Dollar multiplier per volatility unit ($)

    Returns:
        Net EV in dollars. Positive = profitable, Negative = unprofitable.
    """
    ev = (
        savings
        - expected_interruption_cost
        - migration_penalty
        - capacity_failure_risk
        - (normalized_volatility * volatility_cost_multiplier)
    )
    return ev


# ---------------------------------------------------------------------------
# Convenience: Full pipeline in one call
# ---------------------------------------------------------------------------

def evaluate_candidate_ev(
    savings: float,
    final_risk: float,
    normalized_volatility: float,
    # Risk horizon params
    risk_horizon_hours: float = 2.0,
    recovery_time_hours: float = 0.5,
    # Cost params — tuned to real AWS economics
    downtime_cost_per_hour: float = 100.0,
    retry_cost: float = 10.0,
    capacity_failure_probability: float = 0.05,
    drain_time_cost: float = 2.0,
    warmup_cost: float = 1.0,
    control_plane_cost: float = 0.5,
    volatility_cost_multiplier: float = 5.0,
) -> dict:
    """
    Run the complete EV pipeline and return an explainable breakdown.

    This is called by DecisionEngine Step 9 for each candidate pool.
    The breakdown is stored in Redis for audit and UI display.

    Args:
        savings:               Expected hourly savings vs on-demand ($)
        final_risk:            Interruption probability from XGBoost (0.0–1.0)
        normalized_volatility: Price volatility score (0.0–1.0)
        ... (see defaults above for explanation of cost params)

    Returns:
        {
            "ev":                     float  — net EV in dollars
            "savings":                float  — input savings
            "interruption_cost":      float  — expected cost of interruption
            "migration_penalty":      float  — one-time migration overhead
            "capacity_failure_risk":  float  — capacity unavailability cost
            "volatility_cost":        float  — volatility penalty
            "effective_exposure_hours": float
            "is_eligible":            bool   — True if EV > 0
        }
    """
    # §4.1 Risk horizon alignment
    exposure_hours = compute_effective_exposure_hours(risk_horizon_hours, recovery_time_hours)

    # §4.2 Interruption cost
    interruption_cost = compute_expected_interruption_cost(
        final_risk, downtime_cost_per_hour, exposure_hours
    )

    # §4.3 Capacity failure risk
    capacity_risk = compute_capacity_failure_risk(capacity_failure_probability, retry_cost)

    # §4.4 Migration penalty
    migration = compute_migration_penalty(drain_time_cost, warmup_cost, control_plane_cost)

    # Volatility cost
    volatility_cost = normalized_volatility * volatility_cost_multiplier

    # §4.5 Final EV
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
        "is_eligible": ev > 0,  # Decision rule: EV > 0 required
    }
