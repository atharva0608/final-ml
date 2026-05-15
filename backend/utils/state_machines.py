"""
State Machine Utilities
=======================
P-09: Workload Placement State Machine
P-10: Node Lifecycle State Machine
P-11: Pod Lifecycle Classification

All state machines are pure functions with no I/O or DB access.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# P-09 — Workload Placement State Machine
# ---------------------------------------------------------------------------

class PlacementState(str, Enum):
    AT_TARGET = "AT_TARGET"
    CONVERGING = "CONVERGING"
    DRIFTING = "DRIFTING"
    UNKNOWN = "UNKNOWN"


def compute_placement_state(
    current_od: Optional[int],
    ondemand_target: Optional[int],
    last_action: Optional[str],
) -> PlacementState:
    """
    Derive placement state from current OD pod count, OD target, and last decision action.

    Transition rules (priority order):
      1. UNKNOWN      — any input is None
      2. AT_TARGET    — |current_od - ondemand_target| <= 1
      3. CONVERGING   — current_od > ondemand_target AND last_action in ("evict", "rebalance")
      4. DRIFTING     — current_od > ondemand_target AND last_action in ("skip", "defer", None)

    Args:
        current_od:       Current on-demand pod count (from spot:workload:state Redis key).
        ondemand_target:  OD target from PlacementPolicyRecord.ondemand_target.
        last_action:      Most recent decision action from decision log (e.g. "evict", "skip").

    Returns:
        PlacementState enum member.
    """
    if current_od is None or ondemand_target is None:
        return PlacementState.UNKNOWN

    if abs(current_od - ondemand_target) <= 1:
        return PlacementState.AT_TARGET

    if current_od > ondemand_target:
        if last_action in ("evict", "rebalance"):
            return PlacementState.CONVERGING
        return PlacementState.DRIFTING

    return PlacementState.AT_TARGET


# ---------------------------------------------------------------------------
# P-10 — Node Lifecycle States
# ---------------------------------------------------------------------------

class NodeLifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    TERMINATING = "TERMINATING"
    NOT_READY = "NOT_READY"


def compute_node_lifecycle(
    is_ready: Optional[bool],
    do_not_disrupt: Optional[bool],
    has_pending_drain: bool,
) -> NodeLifecycleState:
    """
    Classify a node's lifecycle state.

    Transition rules (priority order):
      1. NOT_READY    — is_ready is False or None
      2. TERMINATING  — has_pending_drain is True AND do_not_disrupt is False
      3. DRAINING     — has_pending_drain is True AND do_not_disrupt is True
      4. ACTIVE       — node is ready and not draining

    Args:
        is_ready:          From NodeMetadata.is_ready.
        do_not_disrupt:    From NodeMetadata.do_not_disrupt.
        has_pending_drain: True if a DRAIN_NODE AgentAction with status PENDING/PICKED_UP
                           exists for this node.

    Returns:
        NodeLifecycleState enum member.
    """
    if not is_ready:
        return NodeLifecycleState.NOT_READY

    if has_pending_drain:
        if do_not_disrupt:
            return NodeLifecycleState.DRAINING
        return NodeLifecycleState.TERMINATING

    return NodeLifecycleState.ACTIVE


# ---------------------------------------------------------------------------
# P-11 — Pod Lifecycle Classification
# ---------------------------------------------------------------------------

IDLE_CPU_THRESHOLD_MILLICORES = 10


class PodLifecycleClass(str, Enum):
    SERVING = "SERVING"
    IDLE = "IDLE"
    EVICTING = "EVICTING"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


def classify_pod_lifecycle(
    phase: Optional[str],
    cpu_usage_millicores: Optional[float],
    has_pending_evict: bool,
) -> PodLifecycleClass:
    """
    Classify a pod's lifecycle state for UI display.

    Transition rules (priority order):
      1. EVICTING     — has_pending_evict is True (EVICT_POD AgentAction in flight)
      2. PENDING      — phase == "Pending"
      3. IDLE         — phase == "Running" AND cpu_usage_millicores < IDLE_CPU_THRESHOLD_MILLICORES
      4. SERVING      — phase == "Running" AND cpu_usage_millicores >= IDLE_CPU_THRESHOLD_MILLICORES
      5. UNKNOWN      — phase is None or unrecognized

    Args:
        phase:                  Pod phase string from pod_metrics (e.g. "Running", "Pending").
        cpu_usage_millicores:   Current CPU usage. None if not measured.
        has_pending_evict:      True if an EVICT_POD AgentAction is in-flight for this pod.

    Returns:
        PodLifecycleClass enum member.
    """
    if has_pending_evict:
        return PodLifecycleClass.EVICTING

    if phase == "Pending":
        return PodLifecycleClass.PENDING

    if phase == "Running":
        if cpu_usage_millicores is not None and cpu_usage_millicores < IDLE_CPU_THRESHOLD_MILLICORES:
            return PodLifecycleClass.IDLE
        return PodLifecycleClass.SERVING

    return PodLifecycleClass.UNKNOWN
