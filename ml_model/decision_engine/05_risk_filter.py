"""
Step 6: Three-Layer Risk Ceiling Filter
=========================================
Source: backend/core/decision_engine.py (lines 346–393)

PURPOSE
-------
Filter out candidate pools whose interruption risk exceeds the configured ceiling.
Uses THREE overlapping safety layers — the STRICTEST one always wins.

WHY THREE LAYERS?
-----------------
A single global risk threshold is too coarse:
  - COST_FIRST clusters accept higher risk (25%) for maximum savings
  - NO_DOWNTIME_FIRST clusters need tighter protection (10%)
  - During market volatility, even COST_FIRST clusters should lower the bar
  - Fresh clusters (< 30 min old) need extra protection — zero trust

THREE-LAYER ARCHITECTURE
--------------------------

  Layer 1: Profile Ceiling (Optimization Mode)
  --------------------------------------------
  Based on user-selected strategy:
    COST_FIRST:       risk_ceiling = 0.25 (accept up to 25% interruption risk)
    BALANCED:         risk_ceiling = 0.20 (default)
    NO_DOWNTIME_FIRST: risk_ceiling = 0.10 (maximum stability)

  Layer 2: Volatility Ceiling Adjustment
  ----------------------------------------
  When the regional spot market is volatile (high price variance):
    Adjustment: -0.05 (lower ceiling by 5%)
    Example: BALANCED 0.20 → 0.15 during volatile market

  Volatility is detected from Redis:
    Key: spot:volatility_regime:{region}
    Value: "true" | "false" (set by intelligence scraper)

  Layer 3: Trust-Phase Override (Progressive Trust)
  ---------------------------------------------------
  Fresh clusters haven't proven stability yet. More restrictive ceiling applies:
    Phase 0 (0-30 min alive):   risk_ceiling = 0.15 (OVERRIDE — most restrictive)
    Phase 1 (30 min - 2h alive): risk_ceiling = 0.20 (OVERRIDE)
    Phase 2 (> 2h alive):        no override (use profile default)

  The MINIMUM of all three layers is used:
    effective_ceiling = min(layer1, layer2_adjusted, layer3_override)

FILTER RESULT
--------------
Any candidate pool with risk_probability > effective_ceiling is removed.
If ALL candidates exceed the ceiling → pipeline returns "risk ceiling exceeded".

EXAMPLE
--------
  Cluster mode: BALANCED (ceiling = 0.20)
  Market: volatile → adjustment -0.05 → layer1+2 = 0.15
  Cluster age: 45 min → phase 1 → override = 0.20
  Effective ceiling = min(0.15, 0.20) = 0.15

  Candidate A: risk = 0.10 → PASSES
  Candidate B: risk = 0.18 → BLOCKED by Layer 2 volatility adjustment
"""

from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Optimization Profiles (Layer 1)
# ---------------------------------------------------------------------------

OPTIMIZATION_PROFILES = {
    "COST_FIRST": {
        "risk_ceiling": 0.25,               # Accept up to 25% risk for max savings
        "delta_threshold": 0.03,            # 3% EV improvement required
        "max_family_ratio": 0.4,            # Max 40% of nodes in single instance family
        "max_az_ratio": 0.5,                # Max 50% of nodes in single AZ
        "capacity_freshness_min": 80,       # Capacity data must be < 80 min old
        "staleness_penalty": 0.95,          # 5% penalty for stale capacity data
        "volatility_ceiling_adjustment": -0.05  # Lower ceiling by 5% in volatile markets
    },
    "BALANCED": {
        "risk_ceiling": 0.20,               # Default: 20% risk ceiling
        "delta_threshold": 0.05,            # 5% EV improvement required
        "max_family_ratio": 0.4,
        "max_az_ratio": 0.5,
        "capacity_freshness_min": 80,
        "staleness_penalty": 0.95,
        "volatility_ceiling_adjustment": -0.05
    },
    "NO_DOWNTIME_FIRST": {
        "risk_ceiling": 0.10,               # Strict: 10% max risk
        "delta_threshold": 0.08,            # 8% EV improvement required (higher bar)
        "max_family_ratio": 0.3,            # Stricter diversity: 30% max per family
        "max_az_ratio": 0.4,                # Stricter AZ diversity: 40% max per AZ
        "capacity_freshness_min": 80,
        "staleness_penalty": 0.95,
        "volatility_ceiling_adjustment": -0.05
    }
}

DEFAULT_PROFILE = "BALANCED"


# ---------------------------------------------------------------------------
# Risk Filter Functions
# ---------------------------------------------------------------------------

def compute_effective_risk_ceiling(
    optimization_mode: str,
    is_volatile_market: bool,
    trust_phase: Optional[dict] = None
) -> float:
    """
    Compute the effective risk ceiling using all three layers.

    The minimum (most restrictive) value from all active layers is used.

    Args:
        optimization_mode:  "COST_FIRST" | "BALANCED" | "NO_DOWNTIME_FIRST"
        is_volatile_market: True if regional spot market is currently volatile
        trust_phase:        Output from OptimizerCoordinator.get_cluster_trust_phase()
                            None = skip Layer 3 (cluster has no phase info)

    Returns:
        Effective risk ceiling (0.0–1.0). Only pools with risk ≤ this pass.

    Example:
        BALANCED (0.20) + volatile (-0.05) = 0.15
        Trust phase 0 override = 0.15
        Effective = min(0.15, 0.15) = 0.15
    """
    # Layer 1: Get profile ceiling
    profile = OPTIMIZATION_PROFILES.get(optimization_mode, OPTIMIZATION_PROFILES[DEFAULT_PROFILE])
    ceiling = profile["risk_ceiling"]

    # Layer 2: Apply volatility adjustment
    if is_volatile_market:
        ceiling += profile["volatility_ceiling_adjustment"]  # Reduces ceiling (adjustment is negative)

    # Layer 3: Trust-phase override (use most restrictive)
    if trust_phase is not None:
        trust_ceiling = trust_phase.get("risk_ceiling_override")
        if trust_ceiling is not None:
            ceiling = min(ceiling, trust_ceiling)

    return ceiling


def check_volatility_regime(redis_client, region: str) -> bool:
    """
    Check if the regional spot market is in a volatile regime.

    The Intelligence Layer (spot_advisor_scraper.py) sets this flag when
    it detects high price variance for a region's spot pools.

    Redis Key: spot:volatility_regime:{region}
    Value:     b"true" or absent (not volatile)

    Args:
        redis_client:  Redis connection
        region:        AWS region e.g. "ap-south-1"

    Returns:
        True if volatile, False otherwise
    """
    cache_key = f"spot:volatility_regime:{region}"
    try:
        is_volatile = redis_client.get(cache_key)
        return is_volatile == b"true" if is_volatile else False
    except Exception:
        return False  # Fail-open: assume stable if Redis is unreachable


def filter_by_risk_ceiling(
    candidate_pools: List[Dict],
    effective_ceiling: float
) -> List[Dict]:
    """
    Remove candidates that exceed the effective risk ceiling.

    Called in DecisionEngine Step 6 after computing the ceiling.

    Args:
        candidate_pools: List of pool dicts with "risk_probability" key
        effective_ceiling: Maximum allowed risk probability (0.0–1.0)

    Returns:
        Filtered list — only pools with risk_probability ≤ effective_ceiling
    """
    return [
        pool for pool in candidate_pools
        if pool.get("risk_probability", 1.0) <= effective_ceiling
    ]


def get_optimization_profile(optimization_mode: str) -> dict:
    """
    Get the full optimization profile for a given mode.

    Used to retrieve other profile settings (delta_threshold, diversity limits, etc.)
    beyond just the risk ceiling.

    Args:
        optimization_mode: "COST_FIRST" | "BALANCED" | "NO_DOWNTIME_FIRST"

    Returns:
        Profile dict with all settings (see OPTIMIZATION_PROFILES above)
    """
    return OPTIMIZATION_PROFILES.get(optimization_mode, OPTIMIZATION_PROFILES[DEFAULT_PROFILE])
