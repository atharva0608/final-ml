"""
Single Source of Truth for Expected Value Scoring
==================================================

Used by:
- pool_ranking_service.py (Intelligence layer)
- decision_engine.py (Policy layer)
- rightsizing_service.py (Recommendations)

Never duplicate this formula elsewhere.
"""

import warnings

# compute_expected_value: DEPRECATED for execution paths.
# Kept for pool ranking sort order only (Tier 1 cache, non-gating).
# compute_combined_expected_value: DEPRECATED.
# Kept as fallback for pre-migration proposals in optimizer_coordinator.py.
# Delete both after migration is confirmed complete.

def compute_expected_value(predicted_savings: float, risk_probability: float) -> float:
    """
    Risk-adjusted expected value. Mathematically stable for ranking.

    Args:
        predicted_savings: Percentage savings (0.0-1.0 range) per node.
                          MUST be per-node normalized. If model outputs absolute $/hr,
                          divide by node count before calling this function.
        risk_probability: Probability of interruption (0.0-1.0 range).

    Returns:
        Expected value score (0.0-1.0 range).

    Formula:
        EV = savings × (1 - risk)

    Example:
        - Pool A: 80% savings, 10% risk → EV = 0.80 × 0.90 = 0.72
        - Pool B: 90% savings, 40% risk → EV = 0.90 × 0.60 = 0.54
        Pool A ranks higher despite lower savings (mathematically stable).

    Why This Works:
        - High savings + high risk gets penalized (Pool B)
        - Low savings + low risk stays competitive (Pool A)
        - No weight tuning needed — pure probability theory

    IMPORTANT:
        The regressor model (regressor_6.onnx) outputs percentage savings (0.0-1.0),
        so this is already normalized per-node. If model changes to absolute values,
        add normalization HERE before computing expected value.
    """
    warnings.warn(
        "compute_expected_value() is deprecated. "
        "Use ev_model.evaluate_candidate_ev() for execution decisions. "
        "This function is kept only for pool ranking cache sort order.",
        DeprecationWarning,
        stacklevel=2
    )

    # Input validation
    if not (0.0 <= predicted_savings <= 1.0):
        raise ValueError(f"predicted_savings must be in [0, 1], got {predicted_savings}")
    if not (0.0 <= risk_probability <= 1.0):
        raise ValueError(f"risk_probability must be in [0, 1], got {risk_probability}")

    # Risk-adjusted expected value
    return predicted_savings * (1.0 - risk_probability)


def compute_combined_expected_value(
    current_size_cost: float,
    current_pool_cost: float,
    current_risk: float,
    new_size_cost: float,
    new_pool_cost: float,
    new_pool_risk: float,
    migration_cost: float = 0.0,
    volatility_penalty: float = 0.0
) -> dict:
    """
    Unified Expected Value calculation for coordinated pool + size optimization.

    Compares three options:
    - Option A: Keep current size, switch to new pool (pool optimization only)
    - Option B: Switch to new size + best pool for that size (combined optimization)
    - Option C: Do nothing (baseline)

    Args:
        current_size_cost: Hourly cost of current instance size ($/hr)
        current_pool_cost: Hourly cost of current pool ($/hr) - may be spot or on-demand
        current_risk: Interruption risk of current pool (0.0-1.0)
        new_size_cost: Hourly cost of proposed rightsizing candidate ($/hr)
        new_pool_cost: Hourly cost of best pool for new size ($/hr)
        new_pool_risk: Interruption risk of new pool (0.0-1.0)
        migration_cost: One-time migration cost ($/instance) - amortized over expected lifetime
        volatility_penalty: Additional penalty for market volatility (0.0-1.0) - reduces EV

    Returns:
        {
            "option_a": {
                "description": "Current size + new pool",
                "hourly_cost": float,
                "hourly_savings": float,
                "risk": float,
                "expected_value": float
            },
            "option_b": {
                "description": "New size + best pool",
                "hourly_cost": float,
                "hourly_savings": float,
                "risk": float,
                "expected_value": float,
                "migration_cost_amortized": float
            },
            "option_c": {
                "description": "Do nothing (baseline)",
                "hourly_cost": float,
                "hourly_savings": float,
                "risk": float,
                "expected_value": float
            },
            "recommended_option": str,  # "A", "B", or "C"
            "best_ev": float,
            "best_ev_delta": float,  # EV improvement over baseline (C)
            "sufficient_improvement": bool  # True if delta >= 10%
        }

    Formula:
        Total EV = (Hourly savings × (1 - risk)) - Migration penalty - Volatility penalty

    Example:
        Current: 4 vCPU / $0.08/hr / 5% risk
        Option A: 4 vCPU + new pool / $0.06/hr / 8% risk → EV = ($0.02 × 0.92) = 0.0184
        Option B: 2 vCPU + best pool / $0.04/hr / 12% risk → EV = ($0.04 × 0.88) - $0.005 = 0.0302

        Option B wins (higher combined EV), despite higher risk.
    """
    warnings.warn(
        "compute_combined_expected_value() is deprecated. "
        "Use ev_model.evaluate_candidate_ev() for execution decisions. "
        "This function is kept as fallback for pre-migration proposals.",
        DeprecationWarning,
        stacklevel=2
    )

    # Input validation
    if current_size_cost <= 0 or current_pool_cost <= 0:
        raise ValueError("Costs must be positive")
    if not (0.0 <= current_risk <= 1.0):
        raise ValueError(f"current_risk must be in [0, 1], got {current_risk}")
    if not (0.0 <= new_pool_risk <= 1.0):
        raise ValueError(f"new_pool_risk must be in [0, 1], got {new_pool_risk}")
    if not (0.0 <= volatility_penalty <= 1.0):
        raise ValueError(f"volatility_penalty must be in [0, 1], got {volatility_penalty}")

    # Baseline (Option C): Do nothing
    baseline_cost = current_pool_cost
    baseline_risk = current_risk

    # Option A: Current size + new pool (pool optimization only)
    option_a_cost = new_pool_cost
    option_a_savings = baseline_cost - option_a_cost
    option_a_risk = new_pool_risk
    option_a_ev = (option_a_savings * (1.0 - option_a_risk)) * (1.0 - volatility_penalty)

    # Option B: New size + best pool for new size (combined optimization)
    option_b_cost = new_pool_cost  # Assuming new_pool_cost is already for the new size
    option_b_savings = baseline_cost - option_b_cost
    option_b_risk = new_pool_risk
    # Amortize migration cost over 720 hours (1 month expected instance lifetime)
    migration_cost_amortized = migration_cost / 720.0 if migration_cost > 0 else 0.0
    option_b_ev = ((option_b_savings - migration_cost_amortized) * (1.0 - option_b_risk)) * (1.0 - volatility_penalty)

    # Option C: Do nothing (baseline)
    option_c_ev = 0.0  # Baseline has 0 additional EV

    # Determine best option
    options = {
        "A": option_a_ev,
        "B": option_b_ev,
        "C": option_c_ev
    }
    best_option = max(options, key=options.get)
    best_ev = options[best_option]
    ev_delta = best_ev - option_c_ev  # Improvement over baseline
    ev_delta_pct = (ev_delta / baseline_cost) * 100 if baseline_cost > 0 else 0.0

    # Check if improvement is sufficient (≥10% threshold per problems.md)
    sufficient_improvement = ev_delta_pct >= 10.0

    return {
        "option_a": {
            "description": "Current size + new pool (pool optimization only)",
            "hourly_cost": option_a_cost,
            "hourly_savings": option_a_savings,
            "risk": option_a_risk,
            "expected_value": option_a_ev
        },
        "option_b": {
            "description": "New size + best pool (combined optimization)",
            "hourly_cost": option_b_cost,
            "hourly_savings": option_b_savings,
            "risk": option_b_risk,
            "expected_value": option_b_ev,
            "migration_cost_amortized": migration_cost_amortized
        },
        "option_c": {
            "description": "Do nothing (baseline)",
            "hourly_cost": baseline_cost,
            "hourly_savings": 0.0,
            "risk": baseline_risk,
            "expected_value": option_c_ev
        },
        "recommended_option": best_option,
        "best_ev": best_ev,
        "best_ev_delta": ev_delta,
        "best_ev_delta_pct": ev_delta_pct,
        "sufficient_improvement": sufficient_improvement
    }
