"""
Optimizer Coordinator — Phase Management + Combined EV
=======================================================
Source: backend/services/optimizer_coordinator.py

PURPOSE
-------
The OptimizerCoordinator is the TOP-LEVEL orchestrator that sequences:
  1. Spot ML Pool Optimization   (the 15-step decision pipeline above)
  2. Right-sizing Optimization   (instance type downsizing via bin-packing)
  3. Combined EV Evaluation      (pool + resize together vs. each alone)

Without this coordinator, the two optimizers would conflict:
  - Pool optimizer drains a node at the same time as right-sizer
  - Right-sizer proposes a resize but pool optimizer switches anyway
  - Both find a "local optimum" but miss the global combined optimum

THE FIVE PHASES
----------------

  Phase 1: INITIAL_POOL_OPTIMIZATION
  ------------------------------------
  - Pool optimizer runs freely (no right-sizing yet)
  - Cluster migrates on-demand nodes to cheapest spot pools
  - Duration: Until first pool switch completes (usually 30–60 min)
  - Right-sizing: BLOCKED (cluster not stable enough)

  Phase 2: STABILIZATION
  -----------------------
  - Wait for cluster to reach steady state after pool changes
  - Duration: 1 hour (configurable)
  - Pool optimizer: allowed (keeps optimizing)
  - Right-sizing: BLOCKED (waiting for stability)

  Phase 3: RIGHTSIZING_EVALUATION
  ---------------------------------
  - Right-sizer proposes a resize (e.g., m5.xlarge → m5.large)
  - Proposal stored in DB as a RightsizingProposal record
  - Pool optimizer: FROZEN (pending_rightsizing_proposal_id set in state)
  - Duration: Until proposal is evaluated (automated or manual)

  Phase 4: COMBINED_EXECUTION
  ----------------------------
  - Evaluate three options:
    Option A: Keep current size + switch spot pool (pool-only optimization)
    Option B: Resize + switch to best spot pool for new size (combined)
    Option C: Do nothing (baseline)
  - Select option with highest expected value (minimum 10% improvement)
  - Execute the chosen option

  Phase 5: COOLDOWN
  ------------------
  - After any execution, enter cooldown
  - Resize cooldown: 6 hours (no new rightsizing)
  - Pool switch cooldown: 30 minutes
  - After cooldown: return to Phase 2 (STABILIZATION) for next cycle

PROGRESSIVE TRUST
------------------
Fresh clusters get extra protection. Trust phases:
  Phase 0 (0–30 min):    No actions. Risk ceiling = 0.15 (tighter than any profile)
  Phase 1 (30 min–2h):   Conservative. Buffer 25%, min 500 metric samples
  Phase 2 (>2h):         Full mode. Buffer 20%, min 100 metric samples

RESIZE CIRCUIT BREAKER
-----------------------
If 3+ resize operations fail within 24 hours, the circuit breaker OPENS:
  - All resize proposals are blocked for the remainder of the 24h window
  - This prevents repeated failed resizes from causing cluster instability
  - Redis Key: resize:failure_count_24h:{cluster_id} (24h TTL)
  - Threshold: 3 failures → open circuit

COMBINED EV CALCULATION
-------------------------
Option A EV: savings(pool_switch_only) × (1 - risk)
Option B EV: savings(resize+pool) × (1 - risk) - migration_penalty
Option C EV: 0.0 (baseline)

The ML system re-runs pool ranking constrained to the proposed instance size
to find the best spot pool FOR THAT SIZE (not just the global best pool).
This is the "combined optimization" — resize shrinks the instance, then
ML finds the cheapest spot pool for the smaller size.

Approval requires: best_ev_delta_pct ≥ 10% over baseline
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Timing configuration
# ---------------------------------------------------------------------------

STABILIZATION_HOURS = 1             # Wait 1h after pool optimization
RIGHTSIZING_EVAL_INTERVAL_HOURS = 24  # Re-evaluate rightsizing at most once/day
MIN_SAVINGS_DELTA_PCT = 10.0        # Minimum 10% EV improvement for combined approval

# Resize circuit breaker threshold
RESIZE_CIRCUIT_BREAKER_THRESHOLD = 3  # Open after 3 failures
RESIZE_FAILURE_WINDOW_HOURS = 24      # Window for counting failures


# ---------------------------------------------------------------------------
# Optimization Phases
# ---------------------------------------------------------------------------

class OptimizationPhase:
    """
    Lifecycle phases for the optimizer coordinator state machine.

    Transitions:
      INITIAL_POOL_OPTIMIZATION → STABILIZATION (after first pool switch)
      STABILIZATION → RIGHTSIZING_EVALUATION (after 1h, if eligible)
      RIGHTSIZING_EVALUATION → COMBINED_EXECUTION (when proposal ready)
      COMBINED_EXECUTION → COOLDOWN (after execution)
      COOLDOWN → STABILIZATION (after cooldown expires)
    """
    INITIAL_POOL_OPTIMIZATION = "INITIAL_POOL_OPTIMIZATION"
    STABILIZATION = "STABILIZATION"
    RIGHTSIZING_EVALUATION = "RIGHTSIZING_EVALUATION"
    COMBINED_EXECUTION = "COMBINED_EXECUTION"
    COOLDOWN = "COOLDOWN"


# ---------------------------------------------------------------------------
# Trust Phase (Progressive Trust)
# ---------------------------------------------------------------------------

def get_cluster_trust_phase(hours_alive: float) -> dict:
    """
    Get the trust phase for a cluster based on its age.

    Newer clusters haven't proven stability — extra restrictions apply.

    Args:
        hours_alive: How many hours the cluster has been running
                     (from OptimizerState.created_at)

    Returns:
        Trust phase dict:
          {
            "phase": 0 | 1 | 2,
            "rightsizing_allowed": bool,
            "safety_buffer_pct": int,   — buffer % added to P95 usage for bin-packing
            "min_samples": int,          — minimum metric samples required
            "risk_ceiling_override": float | None,  — overrides profile risk ceiling
            "reason": str
          }
    """
    if hours_alive < 0.5:       # Phase 0: First 30 minutes
        return {
            "phase": 0,
            "rightsizing_allowed": False,
            "safety_buffer_pct": 30,    # Wide buffer — don't trust early metrics
            "min_samples": 500,         # Need lots of samples before rightsizing
            "risk_ceiling_override": 0.15,  # Tighter than any profile ceiling
            "reason": f"Phase 0: cluster age {hours_alive:.1f}h < 0.5h — observation only"
        }
    elif hours_alive < 2.0:     # Phase 1: 30 min to 2 hours
        return {
            "phase": 1,
            "rightsizing_allowed": True,
            "safety_buffer_pct": 25,    # Conservative buffer
            "min_samples": 500,
            "risk_ceiling_override": 0.20,  # Balanced mode ceiling (safe)
            "reason": f"Phase 1: conservative mode ({hours_alive:.1f}h)"
        }
    else:                       # Phase 2: Over 2 hours (full trust at 24h)
        return {
            "phase": 2,
            "rightsizing_allowed": True,
            "safety_buffer_pct": 20,    # Normal buffer
            "min_samples": 100,         # Fewer samples needed — cluster is proven
            "risk_ceiling_override": None,  # Use profile default (no override)
            "reason": f"Phase 2: full mode ({hours_alive:.1f}h)"
        }


# ---------------------------------------------------------------------------
# Phase gate checks
# ---------------------------------------------------------------------------

def can_run_pool_optimization(
    current_phase: str,
    pending_proposal_id: Optional[str],
    cooldown_active: bool,
    stateless_nodes_exist: bool
) -> Tuple[bool, str]:
    """
    Check if pool optimization can run given current coordinator state.

    Pool optimization is BLOCKED when:
      - A rightsizing proposal is pending (prevent concurrent modifications)
      - Cluster is in RIGHTSIZING_EVALUATION or COMBINED_EXECUTION phase
      - Cluster cooldown is active (another action just ran)
      - No STATELESS_ELIGIBLE nodes exist

    Args:
        current_phase:       Current OptimizationPhase value
        pending_proposal_id: Non-None if a rightsizing proposal is waiting
        cooldown_active:     True if cluster cooldown is active
        stateless_nodes_exist: True if WorkloadInspector found eligible nodes

    Returns:
        (can_run, reason)
    """
    # Pending rightsizing proposal: freeze pool optimization
    # This prevents the pool optimizer from moving a node that the right-sizer
    # wants to resize — they'd conflict and corrupt each other's state.
    if pending_proposal_id:
        return False, "Rightsizing proposal pending — pool optimization frozen"

    # Cooldown check
    if cooldown_active:
        return False, "Cluster cooldown active"

    # Phase check — pool optimization only in these phases
    allowed_phases = {
        OptimizationPhase.INITIAL_POOL_OPTIMIZATION,
        OptimizationPhase.STABILIZATION,
        OptimizationPhase.COOLDOWN,
    }
    if current_phase not in allowed_phases:
        return False, f"Phase {current_phase} does not allow pool optimization"

    # Workload check
    if not stateless_nodes_exist:
        return False, "No stateless-eligible nodes found"

    return True, "Pool optimization allowed"


def can_run_rightsizing_evaluation(
    current_phase: str,
    hours_alive: float,
    hours_since_last_check: Optional[float],
    resize_cooldown_active: bool,
    resize_failure_count: int
) -> Tuple[bool, str]:
    """
    Check if a rightsizing evaluation can run.

    Rightsizing is BLOCKED when:
      - Cluster is in Phase 0 (not old enough)
      - Cluster is in INITIAL_POOL_OPTIMIZATION (first round only)
      - Rightsizing was checked recently (< 24h ago)
      - Resize cooldown is active (< 6h since last resize)
      - Circuit breaker is open (3+ failures in 24h)

    Args:
        current_phase:           Current OptimizationPhase value
        hours_alive:             Cluster age in hours
        hours_since_last_check:  Hours since last rightsizing check (None if never)
        resize_cooldown_active:  True if resize cooldown key exists in Redis
        resize_failure_count:    How many resize failures in last 24h (for circuit breaker)

    Returns:
        (can_run, reason)
    """
    # Trust phase check
    trust = get_cluster_trust_phase(hours_alive)
    if not trust["rightsizing_allowed"]:
        return False, trust["reason"]

    # Phase check
    allowed_phases = {OptimizationPhase.STABILIZATION, OptimizationPhase.COOLDOWN}
    if current_phase not in allowed_phases:
        return False, f"Phase {current_phase} does not allow rightsizing evaluation"

    # Interval check — don't re-evaluate too frequently
    if hours_since_last_check is not None and hours_since_last_check < RIGHTSIZING_EVAL_INTERVAL_HOURS:
        return False, f"Rightsizing evaluated {hours_since_last_check:.1f}h ago (min {RIGHTSIZING_EVAL_INTERVAL_HOURS}h)"

    # Resize cooldown check
    if resize_cooldown_active:
        return False, "Resize cooldown active (6h after last resize)"

    # Circuit breaker check
    if resize_failure_count >= RESIZE_CIRCUIT_BREAKER_THRESHOLD:
        return False, f"Resize circuit breaker open: {resize_failure_count} failures in 24h"

    return True, "Rightsizing evaluation allowed"
