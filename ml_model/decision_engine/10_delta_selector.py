"""
Steps 13–14: Delta Threshold + Best Candidate Selection
=========================================================
Source: backend/core/decision_engine.py (lines 554–625)

PURPOSE
-------
The FINAL two steps of the decision pipeline:
  Step 13: Reject the switch if EV improvement is too small (anti-micro-switch)
  Step 14: Select the best candidate and approve the action

STEP 13: DELTA THRESHOLD (anti-oscillation gate)
-------------------------------------------------
Even after all previous filters, a migration may not be worth executing if
the expected value improvement is tiny. Migrating has real costs:
  - Node drain time (30s–5min)
  - Pod reschedule latency
  - Network reconnection for clients
  - K8s API overhead

If pool B is only 3% better than pool A (BALANCED mode), those costs
may not be worth the improvement — and next cycle might flip back to A.

Delta threshold by optimization mode:
  COST_FIRST:        3% (0.03) — Accept small improvements for max savings
  BALANCED:          5% (0.05) — Default: require meaningful improvement
  NO_DOWNTIME_FIRST: 8% (0.08) — Require large improvement to justify disruption

Formula:
  delta = best_candidate_ev - current_pool_ev
  if delta < delta_threshold → REJECT ("delta below threshold")
  if delta ≥ delta_threshold → APPROVE

Note: This comparison uses the FULL economic EV (from Step 9/02_ev_model.py),
not the simple EV (01_scoring.py). This ensures migration costs are already
factored into the improvement calculation.

STEP 14: CANDIDATE SELECTION + APPROVAL
-----------------------------------------
If the delta threshold is met:
  - The candidate with the highest expected_value is selected
  - The action is approved with full metadata for the Execution Engine
  - Duration (decision latency in ms) is recorded for observability

RETURN STRUCTURE
-----------------
On APPROVE:
  {
    "approved": True,
    "reason": "Action approved",
    "recommendation": {
      "pool": best_candidate_dict,
      "action_type": "POOL_SWITCH",
      "current_pool": current_pool_dict,
      "ev_improvement": delta,
      "optimization_mode": "BALANCED",
      "timestamp": "2026-03-04T10:00:00Z"
    },
    "current_pool_ev": 0.42,
    "best_candidate_ev": 0.67,
    "delta": 0.25,
    "step_completed": "14_approved",
    "duration_ms": 47.3
  }

On REJECT (delta too small):
  {
    "approved": False,
    "reason": "Delta 0.03 below threshold 0.05",
    "recommendation": None,
    "current_pool_ev": 0.42,
    "best_candidate_ev": 0.45,
    "delta": 0.03,
    "step_completed": "13_delta_threshold"
  }
"""

from datetime import datetime
from typing import Dict, List, Optional


def compute_current_pool_ev(current_pool: Dict) -> float:
    """
    Compute EV for the CURRENT pool (what we're running on right now).

    Uses simple EV formula (savings × (1 - risk)) rather than full economic EV.
    This is because migration penalty doesn't apply to staying on the current pool.

    Step 10 in the pipeline: Score current pool BEFORE comparing to candidates.

    Args:
        current_pool: Dict with predicted_savings and risk_probability

    Returns:
        Current pool EV (0.0–1.0), or 0.0 if data is missing
    """
    current_savings = current_pool.get("predicted_savings", 0.0)
    current_risk = current_pool.get("risk_probability", 0.0)

    try:
        # Use simple EV for current pool (no migration cost to stay)
        if not (0.0 <= current_savings <= 1.0):
            return 0.0
        if not (0.0 <= current_risk <= 1.0):
            return 0.0
        return current_savings * (1.0 - current_risk)
    except Exception:
        return 0.0


def apply_delta_threshold(
    sorted_candidates: List[Dict],
    current_pool_ev: float,
    delta_threshold: float
) -> tuple:
    """
    Check if the best candidate improves EV by at least delta_threshold.

    Args:
        sorted_candidates: Candidates sorted descending by expected_value
                           (from Step 9's sort_candidates_by_ev())
        current_pool_ev:   EV of the current pool (Step 10)
        delta_threshold:   Minimum required improvement (from optimization profile)
                           0.03 for COST_FIRST, 0.05 for BALANCED, 0.08 for NO_DOWNTIME

    Returns:
        (best_candidate, best_ev, delta, passes_threshold)
        best_candidate:    Best pool dict, or None if list is empty
        best_ev:           EV of best candidate
        delta:             Improvement over current pool
        passes_threshold:  True if delta ≥ delta_threshold

    Example:
        current_pool_ev = 0.42, best_candidate_ev = 0.67, threshold = 0.05
        delta = 0.67 - 0.42 = 0.25 ≥ 0.05 → PASSES
    """
    if not sorted_candidates:
        return None, 0.0, 0.0, False

    best_candidate = sorted_candidates[0]
    best_ev = best_candidate.get("expected_value", 0.0)
    delta = best_ev - current_pool_ev

    passes = delta >= delta_threshold
    return best_candidate, best_ev, delta, passes


def build_approval_result(
    best_candidate: Dict,
    current_pool: Dict,
    action_type: str,
    delta: float,
    current_pool_ev: float,
    best_candidate_ev: float,
    optimization_mode: str,
    start_time: datetime
) -> Dict:
    """
    Build the final APPROVED result dict returned by DecisionEngine.

    This is the output consumed by the Execution Engine (ml_model/execution_engine/).
    It contains everything needed to execute the pool switch.

    Args:
        best_candidate:    Winning pool dict from Step 13
        current_pool:      Current pool info (for audit trail)
        action_type:       "POOL_SWITCH" | "SCALE_OUT" etc.
        delta:             EV improvement over current pool
        current_pool_ev:   Current pool's EV score
        best_candidate_ev: Best candidate's EV score
        optimization_mode: Which profile was used
        start_time:        When the decision pipeline started (for latency tracking)

    Returns:
        Approved result dict (see module docstring for full schema)
    """
    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

    return {
        "approved": True,
        "reason": "Action approved",
        "recommendation": {
            "pool": best_candidate,
            "action_type": action_type,
            "current_pool": current_pool,
            "ev_improvement": delta,
            "optimization_mode": optimization_mode,
            "timestamp": datetime.utcnow().isoformat()
        },
        "current_pool_ev": current_pool_ev,
        "best_candidate_ev": best_candidate_ev,
        "delta": delta,
        "step_completed": "14_approved",
        "duration_ms": duration_ms
    }


def build_rejection_result(
    reason: str,
    step: str,
    current_pool_ev: float = 0.0,
    best_candidate_ev: float = 0.0,
    delta: float = 0.0
) -> Dict:
    """
    Build a standardized REJECTED result dict.

    Returned by any step in the pipeline when action is blocked.
    All rejection results have the same shape regardless of which step blocked.

    Args:
        reason:            Human-readable explanation for the block
        step:              Which step blocked the action (e.g. "6_risk_ceiling")
        current_pool_ev:   Current pool EV (0.0 if not yet computed)
        best_candidate_ev: Best candidate EV (0.0 if not yet computed)
        delta:             EV delta (0.0 if not yet computed)

    Returns:
        Rejection result dict (approved=False)
    """
    return {
        "approved": False,
        "reason": reason,
        "recommendation": None,
        "current_pool_ev": current_pool_ev,
        "best_candidate_ev": best_candidate_ev,
        "delta": delta,
        "step_completed": step
    }
