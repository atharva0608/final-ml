"""
Step 9: Pool Re-Scorer (Full Economic EV)
==========================================
Source: backend/core/decision_engine.py (lines 427–463)
Uses:   backend/core/ev_model.py

PURPOSE
-------
Re-score all remaining candidate pools using the full economic EV model.
This is the core ML scoring step — it goes beyond simple savings × (1-risk)
to account for real AWS economic factors.

WHY RE-SCORE HERE?
-------------------
By Step 9, the candidate list has been filtered by:
  - Cooldowns (Steps 1-2)
  - Node classification (Steps 2b-2c)
  - Risk ceiling (Step 6)
  - Capacity freshness (Step 7)

The candidates have also had their predicted_savings potentially penalized
(Step 7 staleness penalty). Re-scoring with the full EV model at THIS point
ensures the final ranking reflects all adjustments made by earlier steps.

Additionally, the dynamic capacity failure probability (Step 9.1) is read
from Redis here — it reflects LIVE DryRun failure rates, not static assumptions.

SCORING PIPELINE (per pool)
-----------------------------
For each candidate pool:
  1. Read dynamic capacity failure probability from Redis (live DryRun data)
  2. Run evaluate_candidate_ev() from 02_ev_model.py with all economic factors
  3. If EV > 0: mark as eligible, store ev_breakdown on pool dict
  4. If EV ≤ 0: remove from candidates (pool costs more than it saves)

WHAT MAKES A POOL ELIGIBLE?
-----------------------------
  EV > 0 means:
    Savings > (Interruption Cost + Migration Penalty + Capacity Risk + Volatility)

  If a pool's EV is negative, migrating to it would COST money in expectation —
  even accounting for the spot discount. This happens when:
    - Risk is very high (interruption cost dominates)
    - Price is only marginally cheaper (small savings, high fixed migration cost)
    - Market is highly volatile (volatility penalty dominates)

OUTPUT
------
Returns only eligible candidates (EV > 0) with:
  pool["expected_value"] = ev_breakdown["ev"]
  pool["ev_breakdown"] = {ev, savings, interruption_cost, ...}

The pool with the highest expected_value is selected in Step 13-14.
"""

from typing import List, Dict, Optional
from backend.core.ev_model import evaluate_candidate_ev, get_dynamic_capacity_failure_probability


# ---------------------------------------------------------------------------
# Default economic parameters (can be overridden by cluster config)
# ---------------------------------------------------------------------------

DEFAULT_EV_PARAMS = {
    "downtime_cost_per_hour": 100.0,     # $100/hr SLA penalty per affected node
    "risk_horizon_hours": 2.0,           # Evaluate risk over 2-hour window
    "recovery_time_hours": 0.5,          # 30 min to provision replacement
    "retry_cost": 10.0,                  # $10 on-demand retry if capacity fails
    "drain_time_cost": 2.0,              # $2 for graceful drain overhead
    "warmup_cost": 1.0,                  # $1 application warmup cost
    "control_plane_cost": 0.5,           # $0.50 Kubernetes API overhead
    "volatility_cost_multiplier": 5.0,   # $5 per unit of normalized volatility
}


def score_candidates_with_full_ev(
    candidate_pools: List[Dict],
    redis_client,
    region: str,
    ev_params: Optional[Dict] = None
) -> List[Dict]:
    """
    Re-score all candidates using the full economic EV model.

    Eligible candidates (EV > 0) are returned with their EV breakdown.
    Ineligible candidates (EV ≤ 0) are silently dropped.

    Args:
        candidate_pools: Filtered pool dicts from Steps 2-7.
                         Each must have: predicted_savings, risk_probability,
                         normalized_volatility, instance_type, az
        redis_client:    Redis connection (for dynamic capacity failure rate)
        region:          AWS region e.g. "ap-south-1"
        ev_params:       Override economic parameters (optional).
                         Defaults to DEFAULT_EV_PARAMS.

    Returns:
        List of eligible pool dicts (EV > 0), with added keys:
          pool["expected_value"]  — net EV in dollars (higher = better)
          pool["ev_breakdown"]    — full economic breakdown dict

    Notes:
        - Pools with EV ≤ 0 are dropped silently (not an error condition)
        - Dynamic capacity failure rate from Redis reflects live DryRun data
        - If EV calculation fails for a pool, that pool gets expected_value=0.0
    """
    params = {**DEFAULT_EV_PARAMS, **(ev_params or {})}

    eligible_candidates = []

    for pool in candidate_pools:
        predicted_savings = pool.get("predicted_savings", 0.0)
        risk_probability = pool.get("risk_probability", 0.0)
        normalized_volatility = pool.get("normalized_volatility", 0.0)
        pool_id = f"{pool.get('instance_type', '')}:{pool.get('az', '')}"

        try:
            # Step 9.1: Read live DryRun failure rate from Redis
            # This is a dynamic signal — higher failure rate = higher capacity risk
            cap_fail_prob = get_dynamic_capacity_failure_probability(
                redis_client, pool_id, region
            )

            # Step 9.2: Run full economic EV computation
            ev_breakdown = evaluate_candidate_ev(
                savings=predicted_savings,
                final_risk=risk_probability,
                normalized_volatility=normalized_volatility,
                capacity_failure_probability=cap_fail_prob,
                **{k: v for k, v in params.items() if k != "capacity_failure_probability"}
            )

            # Step 9.3: Apply decision rule: EV > 0 = eligible
            if not ev_breakdown["is_eligible"]:
                # Pool costs more than it saves — drop it
                continue

            # Store EV data on pool dict for Steps 10-14
            pool["expected_value"] = ev_breakdown["ev"]
            pool["ev_breakdown"] = ev_breakdown
            eligible_candidates.append(pool)

        except Exception as e:
            # Scoring error — pool gets EV=0.0 (won't be selected)
            pool["expected_value"] = 0.0

    return eligible_candidates


def sort_candidates_by_ev(candidates: List[Dict]) -> List[Dict]:
    """
    Sort candidates by expected_value descending (best first).

    Called after score_candidates_with_full_ev() and before Step 13 (delta check).
    The first element after sorting is the best candidate.

    Args:
        candidates: List of eligible pool dicts with expected_value set

    Returns:
        Same list, sorted descending by expected_value
    """
    return sorted(candidates, key=lambda p: p.get("expected_value", 0.0), reverse=True)
