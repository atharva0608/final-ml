"""
Guardrail Engine — Hard Constraints & Safety Checks
====================================================
Implements problems.md §5:
  §5.1 Hard Guards (spot ratio, AZ concentration, family concentration, spend cap,
                    concurrent nodes down, maintenance window, stateful block)
  §5.2 Spend Velocity Guard
  §5.3 Stabilization Guard
  §5.4 Cluster Health Score
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ──────────────────────────────────────────────────────────────────
# §5.1  Hard Guards
# ──────────────────────────────────────────────────────────────────

DEFAULT_HARD_GUARDS = {
    "max_spot_ratio": 0.80,           # 80% spot ceiling
    "max_az_concentration": 0.60,     # No AZ > 60% of spot nodes
    "max_family_concentration": 0.50, # No instance family > 50%
    "daily_spend_cap_usd": 10000.0,   # $10k/day default
    "max_concurrent_nodes_down": 3,   # max simultaneous drains
}


def check_hard_guards(
    spot_ratio: float,
    az_concentration: float,
    family_concentration: float,
    daily_spend_usd: float,
    concurrent_nodes_down: int,
    is_stateful_node: bool,
    is_maintenance_window: bool,
    config: Optional[Dict] = None,
) -> Tuple[bool, List[str]]:
    """
    Check all hard guards. Returns (passed, list_of_violations).
    ALL must pass for the action to proceed.

    Args:
        spot_ratio:             Current spot nodes / total nodes [0,1].
        az_concentration:       Highest AZ concentration [0,1].
        family_concentration:   Highest instance family concentration [0,1].
        daily_spend_usd:        Total spend so far today in USD.
        concurrent_nodes_down:  Current count of nodes being drained.
        is_stateful_node:       True if target node carries stateful workload.
        is_maintenance_window:  True if we are NOT in a safe maintenance window
                                (i.e., destructive ops are blocked outside window).
        config:                 Optional override dict for threshold values.

    Returns:
        (all_passed: bool, violations: List[str])
    """
    cfg = {**DEFAULT_HARD_GUARDS, **(config or {})}
    violations: List[str] = []

    if spot_ratio >= cfg["max_spot_ratio"]:
        violations.append(
            f"Spot ratio {spot_ratio:.0%} >= limit {cfg['max_spot_ratio']:.0%}"
        )

    if az_concentration >= cfg["max_az_concentration"]:
        violations.append(
            f"AZ concentration {az_concentration:.0%} >= limit {cfg['max_az_concentration']:.0%}"
        )

    if family_concentration >= cfg["max_family_concentration"]:
        violations.append(
            f"Family concentration {family_concentration:.0%} >= limit {cfg['max_family_concentration']:.0%}"
        )

    if daily_spend_usd >= cfg["daily_spend_cap_usd"]:
        violations.append(
            f"Daily spend ${daily_spend_usd:,.0f} >= cap ${cfg['daily_spend_cap_usd']:,.0f}"
        )

    if concurrent_nodes_down >= cfg["max_concurrent_nodes_down"]:
        violations.append(
            f"Concurrent drains {concurrent_nodes_down} >= max {cfg['max_concurrent_nodes_down']}"
        )

    if is_stateful_node:
        violations.append("Stateful node — auto-scaling blocked (requires manual approval)")

    if is_maintenance_window:
        violations.append("Maintenance window active — destructive operations blocked")

    return (len(violations) == 0, violations)


# ──────────────────────────────────────────────────────────────────
# §5.2  Spend Velocity Guard
# ──────────────────────────────────────────────────────────────────

def calculate_spend_velocity(
    hourly_cost_now: float,
    hourly_cost_1h_ago: float,
) -> float:
    """
    SpendVelocity = HourlyCostNow - HourlyCost1hAgo

    Positive = costs are rising.
    """
    return hourly_cost_now - hourly_cost_1h_ago


def check_spend_velocity_guard(
    hourly_cost_now: float,
    hourly_cost_1h_ago: float,
    velocity_threshold_usd: float = 50.0,
    proposed_action: str = "any",
) -> Tuple[bool, str]:
    """
    If spend velocity exceeds threshold:
      - Block upward resizes (scale-up)
      - Allow downward resizes (scale-down) — they reduce cost

    Returns (action_allowed, reason).
    """
    velocity = calculate_spend_velocity(hourly_cost_now, hourly_cost_1h_ago)

    if velocity > velocity_threshold_usd:
        if proposed_action in ("upsize", "scale_up", "add_node"):
            return (
                False,
                f"Spend velocity ${velocity:+.2f}/hr exceeds threshold — upward resizes blocked",
            )
        return (
            True,
            f"Spend velocity ${velocity:+.2f}/hr elevated but downward action allowed",
        )

    return (True, f"Spend velocity ${velocity:+.2f}/hr within threshold")


# ── Task 6.1: Org-Level Spend Velocity Guard ─────────────────────

def check_org_spend_velocity_guard(
    redis_client,
    org_id: str,
    proposed_action: str = "any",
    org_velocity_threshold_usd: float = 200.0,
) -> Tuple[bool, str]:
    """
    Org-level spend velocity guard — checks total spend across ALL clusters
    in an organization. If total velocity exceeds threshold, block upward
    resizes to prevent runaway cost escalation.

    Args:
        redis_client: Redis client instance
        org_id: Organization identifier
        proposed_action: Type of action being attempted
        org_velocity_threshold_usd: Threshold in $/hr across entire org

    Returns:
        (action_allowed, reason)
    """
    try:
        org_velocity_key = f"spot:org_spend_velocity:{org_id}"
        raw = redis_client.get(org_velocity_key)
        org_velocity = float(raw) if raw else 0.0

        if org_velocity > org_velocity_threshold_usd:
            if proposed_action in ("upsize", "scale_up", "add_node"):
                return (
                    False,
                    f"Org spend velocity ${org_velocity:+.2f}/hr exceeds "
                    f"${org_velocity_threshold_usd}/hr — upward resizes blocked"
                )
            return (
                True,
                f"Org spend velocity elevated (${org_velocity:+.2f}/hr) "
                f"but downward action allowed"
            )

        return (True, f"Org spend velocity ${org_velocity:+.2f}/hr within threshold")
    except Exception as e:
        # Fail open on Redis errors
        return (True, f"Org spend velocity check failed: {e} (fail-open)")


# ──────────────────────────────────────────────────────────────────
# §5.3  Stabilization Guard
# ──────────────────────────────────────────────────────────────────

def check_stabilization_guard(
    last_execution_time: Optional[datetime],
    stabilization_minutes: float = 3.0,
) -> Tuple[bool, float]:
    """
    After execution wait 2–5 min before allowing next action.
    Returns (stabilized, minutes_remaining).
    """
    if last_execution_time is None:
        return (True, 0.0)

    elapsed = (datetime.utcnow() - last_execution_time).total_seconds() / 60.0
    remaining = max(stabilization_minutes - elapsed, 0.0)
    return (remaining == 0.0, round(remaining, 1))


# ──────────────────────────────────────────────────────────────────
# §5.4  Cluster Health Score
# ──────────────────────────────────────────────────────────────────

HEALTH_SCORE_THRESHOLD = 0.75


def _normalize_pending_pods(pending_pods: int, total_pods: int) -> float:
    """Higher pending = lower score."""
    if total_pods <= 0:
        return 1.0
    ratio = pending_pods / total_pods
    return max(1.0 - ratio, 0.0)


def _normalize_node_ready_ratio(ready_nodes: int, total_nodes: int) -> float:
    if total_nodes <= 0:
        return 1.0
    return min(ready_nodes / total_nodes, 1.0)


def _normalize_latency_delta(latency_delta_pct: float) -> float:
    """latency_delta_pct: % increase vs baseline.  0 = no change = 1.0 score."""
    if latency_delta_pct <= 0:
        return 1.0
    return max(1.0 - latency_delta_pct / 100.0, 0.0)


def _normalize_cpu_headroom(cpu_headroom_pct: float) -> float:
    """cpu_headroom_pct: how much CPU is free (0–100)."""
    return min(cpu_headroom_pct / 100.0, 1.0)


def calculate_cluster_health_score(
    pending_pods: int,
    total_pods: int,
    ready_nodes: int,
    total_nodes: int,
    latency_delta_pct: float = 0.0,
    cpu_headroom_pct: float = 50.0,
) -> dict:
    """
    Cluster Health Score = 0.25×Pending + 0.25×Ready + 0.25×Latency + 0.25×Headroom
    Requires >= 0.75 to proceed.

    Returns:
        {score, is_healthy, components}
    """
    pending_score  = _normalize_pending_pods(pending_pods, total_pods)
    ready_score    = _normalize_node_ready_ratio(ready_nodes, total_nodes)
    latency_score  = _normalize_latency_delta(latency_delta_pct)
    headroom_score = _normalize_cpu_headroom(cpu_headroom_pct)

    score = (
        0.25 * pending_score
        + 0.25 * ready_score
        + 0.25 * latency_score
        + 0.25 * headroom_score
    )

    return {
        "score": round(score, 4),
        "is_healthy": score >= HEALTH_SCORE_THRESHOLD,
        "threshold": HEALTH_SCORE_THRESHOLD,
        "components": {
            "pending_score":  round(pending_score, 4),
            "ready_score":    round(ready_score, 4),
            "latency_score":  round(latency_score, 4),
            "headroom_score": round(headroom_score, 4),
        },
    }


# ──────────────────────────────────────────────────────────────────
# Composite Guard Evaluation
# ──────────────────────────────────────────────────────────────────

def evaluate_all_guardrails(
    spot_ratio: float,
    az_concentration: float,
    family_concentration: float,
    daily_spend_usd: float,
    concurrent_nodes_down: int,
    is_stateful_node: bool,
    is_maintenance_window: bool,
    hourly_cost_now: float,
    hourly_cost_1h_ago: float,
    pending_pods: int,
    total_pods: int,
    ready_nodes: int,
    total_nodes: int,
    latency_delta_pct: float = 0.0,
    cpu_headroom_pct: float = 50.0,
    last_execution_time: Optional[datetime] = None,
    proposed_action: str = "pool_switch",
    guard_config: Optional[Dict] = None,
) -> dict:
    """
    Run ALL guardrails and return comprehensive result dict.

    Returns:
        {
            all_passed, hard_guard_passed, spend_velocity_passed,
            stabilization_passed, health_passed,
            violations, health_score, stabilization_remaining_min
        }
    """
    hard_passed, violations = check_hard_guards(
        spot_ratio, az_concentration, family_concentration,
        daily_spend_usd, concurrent_nodes_down,
        is_stateful_node, is_maintenance_window,
        config=guard_config,
    )

    velocity_passed, velocity_reason = check_spend_velocity_guard(
        hourly_cost_now, hourly_cost_1h_ago, proposed_action=proposed_action
    )
    if not velocity_passed:
        violations.append(velocity_reason)

    stabilized, remaining = check_stabilization_guard(last_execution_time)
    if not stabilized:
        violations.append(f"Stabilization window: {remaining:.1f} min remaining")

    health = calculate_cluster_health_score(
        pending_pods, total_pods, ready_nodes, total_nodes,
        latency_delta_pct, cpu_headroom_pct
    )
    if not health["is_healthy"]:
        violations.append(
            f"Cluster health score {health['score']:.2f} below threshold {HEALTH_SCORE_THRESHOLD}"
        )

    all_passed = hard_passed and velocity_passed and stabilized and health["is_healthy"]

    return {
        "all_passed": all_passed,
        "hard_guard_passed": hard_passed,
        "spend_velocity_passed": velocity_passed,
        "stabilization_passed": stabilized,
        "health_passed": health["is_healthy"],
        "violations": violations,
        "health_score": health,
        "stabilization_remaining_min": remaining,
    }
