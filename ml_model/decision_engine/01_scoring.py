"""
Step 0: Core Expected Value Scoring Formula
============================================
Source: backend/core/scoring.py

PURPOSE
-------
Single source of truth for the risk-adjusted Expected Value (EV) formula.
Used across ALL layers of the system:
  - Intelligence Layer (pool ranking, sorting candidates)
  - Decision Engine (comparing current pool vs. best candidate)
  - Rightsizing Service (evaluating resize proposals)

NEVER duplicate this formula anywhere else. If the formula changes,
update it here and the change propagates everywhere automatically.

FORMULA
-------
    EV = predicted_savings × (1 - risk_probability)

  Where:
    predicted_savings:  0.0–1.0 (% cost saved vs on-demand baseline)
    risk_probability:   0.0–1.0 (probability of interruption in 2h window)

EXAMPLE
-------
    Pool A: 80% savings, 10% risk  →  EV = 0.80 × 0.90 = 0.72  (winner)
    Pool B: 90% savings, 40% risk  →  EV = 0.90 × 0.60 = 0.54

  Pool A ranks higher despite lower savings because interruption cost
  outweighs the extra savings from Pool B.

NOTE: For actual execution decisions, use the full economic EV model in
02_ev_model.py (which adds interruption cost, migration penalty, etc.).
This simpler formula is used for sorting/ranking only.
"""


def compute_expected_value(predicted_savings: float, risk_probability: float) -> float:
    """
    Risk-adjusted expected value for pool ranking.

    Args:
        predicted_savings:  Fractional savings 0.0–1.0. Must be normalized
                            per-node. If the ML model outputs absolute $/hr,
                            divide by node count before calling this function.
        risk_probability:   Interruption probability 0.0–1.0 (from XGBoost regressor).

    Returns:
        EV score in 0.0–1.0 range. Higher = better candidate.

    Raises:
        ValueError: If inputs are outside [0, 1] range.

    Notes:
        - The XGBoost model (regressor_6.onnx) already outputs per-node
          normalized savings (0.0–1.0), so no additional normalization needed.
        - This function is intentionally kept simple. Complex economic
          factors (downtime cost, migration cost) are in 02_ev_model.py.
    """
    # Input validation — catch bugs early
    if not (0.0 <= predicted_savings <= 1.0):
        raise ValueError(f"predicted_savings must be in [0, 1], got {predicted_savings}")
    if not (0.0 <= risk_probability <= 1.0):
        raise ValueError(f"risk_probability must be in [0, 1], got {risk_probability}")

    # Core EV formula: risk-adjusted savings
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
    Combined EV for coordinated pool + rightsizing optimization.

    Used by OptimizerCoordinator to compare three options:
      Option A: Keep current size, switch spot pool (pool optimization only)
      Option B: Resize instance + switch to best spot pool (combined)
      Option C: Do nothing (baseline)

    Args:
        current_size_cost:  Current instance hourly cost ($/hr)
        current_pool_cost:  Current spot pool hourly cost ($/hr)
        current_risk:       Current pool interruption risk (0.0–1.0)
        new_size_cost:      Proposed rightsized instance hourly cost ($/hr)
        new_pool_cost:      Best spot pool cost for new size ($/hr)
        new_pool_risk:      Interruption risk for new pool (0.0–1.0)
        migration_cost:     One-time migration cost in dollars, amortized
                            over 720 hours (1 month expected lifetime)
        volatility_penalty: Market volatility penalty (0.0–1.0), reduces EV

    Returns:
        Dict with keys:
          option_a, option_b, option_c — each with hourly_cost, ev, etc.
          recommended_option — "A", "B", or "C"
          best_ev, best_ev_delta, best_ev_delta_pct
          sufficient_improvement — True if delta ≥ 10% (threshold per spec)

    Decision threshold: 10% minimum EV improvement required to approve action.
    """
    if current_size_cost <= 0 or current_pool_cost <= 0:
        raise ValueError("Costs must be positive")
    if not (0.0 <= current_risk <= 1.0):
        raise ValueError(f"current_risk must be in [0, 1], got {current_risk}")
    if not (0.0 <= new_pool_risk <= 1.0):
        raise ValueError(f"new_pool_risk must be in [0, 1], got {new_pool_risk}")
    if not (0.0 <= volatility_penalty <= 1.0):
        raise ValueError(f"volatility_penalty must be in [0, 1], got {volatility_penalty}")

    baseline_cost = current_pool_cost
    baseline_risk = current_risk

    # Option A: keep size, switch pool
    option_a_savings = baseline_cost - new_pool_cost
    option_a_ev = (option_a_savings * (1.0 - new_pool_risk)) * (1.0 - volatility_penalty)

    # Option B: resize + switch pool (migration cost amortized over 720h)
    option_b_savings = baseline_cost - new_pool_cost
    migration_cost_amortized = migration_cost / 720.0 if migration_cost > 0 else 0.0
    option_b_ev = ((option_b_savings - migration_cost_amortized) * (1.0 - new_pool_risk)) * (1.0 - volatility_penalty)

    # Option C: do nothing
    option_c_ev = 0.0

    options = {"A": option_a_ev, "B": option_b_ev, "C": option_c_ev}
    best_option = max(options, key=options.get)
    best_ev = options[best_option]
    ev_delta = best_ev - option_c_ev
    ev_delta_pct = (ev_delta / baseline_cost) * 100 if baseline_cost > 0 else 0.0
    sufficient_improvement = ev_delta_pct >= 10.0  # 10% threshold from spec

    return {
        "option_a": {
            "description": "Current size + new pool (pool optimization only)",
            "hourly_cost": new_pool_cost,
            "hourly_savings": option_a_savings,
            "risk": new_pool_risk,
            "expected_value": option_a_ev
        },
        "option_b": {
            "description": "New size + best pool (combined optimization)",
            "hourly_cost": new_pool_cost,
            "hourly_savings": option_b_savings,
            "risk": new_pool_risk,
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
