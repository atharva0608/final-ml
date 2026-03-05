"""
Step 7: Capacity Freshness Validation
=======================================
Source: backend/core/decision_engine.py (lines 396–415)

PURPOSE
-------
Penalize candidate pools whose capacity data is stale (older than threshold).

WHY FRESHNESS MATTERS
-----------------------
The ML model predicts spot savings based on recent AWS spot price data.
If the price data is too old, the prediction may be wrong:
  - A pool that was cheap 2 hours ago may now be expensive
  - AWS spot prices change every 15 seconds in real-time
  - Making a migration decision on stale data = financial risk

TWO STALENESS CHECKS
---------------------

  1. Pricing Freshness (Step 1b in pipeline)
     ----------------------------------------
     Checks the timestamp of the REGIONAL spot price update in Redis:
       Key: pricing:last_updated:{region}
       Max age: 15 minutes
     If pricing data is older than 15 minutes → HARD REJECT (pipeline blocked)
     This is a hard block because prices fluctuate minute-by-minute.

  2. Capacity Data Freshness (Step 7 in pipeline)
     ------------------------------------------------
     Checks per-pool capacity data age (from AWS DescribeInstanceTypeOfferings):
       Field: pool["capacity_age_minutes"]
       Max age: 80 minutes (from optimization profile)
     If capacity data is stale → SOFT PENALTY: multiply predicted_savings by 0.95
     This is a soft penalty because capacity availability changes slower than prices.

STALENESS PENALTY
------------------
When capacity data exceeds freshness_threshold_min:
  pool["predicted_savings"] *= staleness_penalty  (default 0.95 = 5% reduction)

This makes the pool appear slightly less attractive → it may lose to fresher pools
in the EV scoring phase, but is not completely blocked.

Example:
  Pool A: 60% savings, capacity 2 hours old → penalized to 57% (60 × 0.95)
  Pool B: 55% savings, fresh capacity data → stays at 55%
  EV comparison: A (0.57 × 0.9) = 0.513 vs B (0.55 × 0.92) = 0.506
  Pool A still wins despite penalty (higher savings outweigh staleness)

IMPLEMENTATION NOTE
--------------------
This step modifies pool dicts in-place (adds staleness_penalty_applied=True flag).
The modified dicts are passed to Step 9 (EV scoring) with the penalized savings.
"""

from typing import List, Dict
from datetime import datetime


# ---------------------------------------------------------------------------
# Freshness check for regional pricing data (Step 1b — hard reject)
# ---------------------------------------------------------------------------

PRICING_MAX_AGE_MINUTES = 15  # Hard reject if pricing data older than this


def check_pricing_freshness(redis_client, region: str) -> tuple:
    """
    Check if regional spot pricing data is fresh enough to make decisions.

    If pricing data is stale (> 15 min), the entire pipeline is blocked.
    This prevents making migration decisions based on outdated prices.

    Redis Key: pricing:last_updated:{region}
    Value:     ISO timestamp string (set by spot price scraper)

    Args:
        redis_client:  Redis connection
        region:        AWS region e.g. "ap-south-1"

    Returns:
        (is_fresh, staleness_minutes)
        is_fresh=True → pricing is current, proceed
        is_fresh=False → pricing is stale, block action
    """
    pricing_key = f"pricing:last_updated:{region}"

    try:
        last_updated_raw = redis_client.get(pricing_key)
        if not last_updated_raw:
            # No timestamp = no price data has been loaded yet
            # Fail-OPEN: allow execution (don't block on first run)
            return True, 0.0

        last_updated = datetime.fromisoformat(
            last_updated_raw.decode("utf-8") if isinstance(last_updated_raw, bytes)
            else last_updated_raw
        )
        staleness_minutes = (datetime.utcnow() - last_updated).total_seconds() / 60

        is_fresh = staleness_minutes <= PRICING_MAX_AGE_MINUTES
        return is_fresh, staleness_minutes

    except Exception:
        # Fail-open: allow execution if timestamp parsing fails
        return True, 0.0


# ---------------------------------------------------------------------------
# Capacity data freshness (Step 7 — soft penalty)
# ---------------------------------------------------------------------------

def apply_capacity_staleness_penalty(
    candidate_pools: List[Dict],
    freshness_threshold_min: int = 80,
    staleness_penalty: float = 0.95
) -> List[Dict]:
    """
    Apply staleness penalty to candidates with old capacity data.

    Modifies pool dicts in-place: reduces predicted_savings by penalty factor.
    Adds "staleness_penalty_applied": True flag to penalized pools.

    Called in DecisionEngine Step 7, BEFORE EV scoring (Step 9).
    This ensures the EV calculation uses the adjusted (penalized) savings.

    Args:
        candidate_pools:       List of pool dicts (modified in-place)
        freshness_threshold_min: Max acceptable capacity data age in minutes
        staleness_penalty:      Multiplier for old data (0.95 = 5% reduction)

    Returns:
        Same list (modified in-place, returned for chaining)

    Side effects:
        - pool["predicted_savings"] reduced if stale
        - pool["staleness_penalty_applied"] = True added if penalized

    Example:
        Pool with capacity_age_minutes=120, predicted_savings=0.60:
          → penalized savings = 0.60 × 0.95 = 0.57
          → staleness_penalty_applied = True
    """
    for pool in candidate_pools:
        capacity_age_min = pool.get("capacity_age_minutes", 0)

        if capacity_age_min > freshness_threshold_min:
            # Apply staleness penalty to predicted savings
            original_savings = pool.get("predicted_savings", 0.0)
            pool["predicted_savings"] = original_savings * staleness_penalty
            pool["staleness_penalty_applied"] = True

    return candidate_pools
