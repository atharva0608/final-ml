"""
TargetBuilder — WIE → PPE translation layer.
=============================================
Thin layer between WorkloadIdentificationEngine and PodPlacementEngine.

Translates a list of WorkloadClassification objects (WIE output) into
PlacementTarget objects (PPE input) by comparing desired distribution
(min_on_demand_replicas / max_spot_replicas) against the current live
state of each workload's pods.

Key contract:
  - action_required = False  →  workload already at target, PPE skips it
  - delta_od > 0             →  need to move pods from spot → OD
  - delta_spot > 0           →  need to move pods from OD → spot
  - delta_od < 0 OR
    delta_spot < 0           →  overshoot (rebalance needed)

Pure-function module — no Redis/DB writes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlacementTarget:
    """PPE-consumable target for a single workload."""
    namespace: str
    controller_name: str
    controller_kind: str
    workload_class: str          # "db" | "stateful" | "stateless" | "mixed"

    # Desired state (from WIE)
    od_target: int               # exact OD replica count PPE must achieve
    spot_target: int             # exact spot replica count PPE must achieve
    total_replicas: int

    # Current live state (derived from live pods + nodes)
    current_od_count: int
    current_spot_count: int
    current_unknown_count: int   # pods on nodes with unresolved capacity type

    # Deltas — positive = need more of that type
    delta_od: int                # od_target - current_od_count
    delta_spot: int              # spot_target - current_spot_count

    # Gate: False → PPE skips this workload entirely
    action_required: bool

    # Debug / audit
    signals: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_node_capacity_map(live_nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Returns {node_name: normalized_capacity_type}.
    Normalized to "spot" or "on-demand".
    """
    cap_map: Dict[str, str] = {}
    for n in live_nodes:
        name = n.get("node_name") or n.get("name")
        if not name:
            continue
        raw = (n.get("capacity_type") or "").lower()
        cap_map[name] = "spot" if "spot" in raw else "on-demand"
    return cap_map


def _get_controller_name(pod: Dict[str, Any]) -> Optional[str]:
    """
    Derive controller name from pod metadata.
    Checks controller_name field first, then strips pod ordinal suffix as fallback.
    """
    ctrl = pod.get("controller_name") or pod.get("workload_name")
    if ctrl:
        return ctrl
    pod_name = pod.get("pod_name") or ""
    # Strip the last 1–2 random suffixes: myapp-7d4b9c-xkj2p → myapp
    # StatefulSet pods: myapp-0 → myapp (strip ordinal only)
    parts = pod_name.rsplit("-", 2)
    return parts[0] if len(parts) >= 2 else pod_name


def _count_pod_capacity_types(
    namespace: str,
    controller_name: str,
    live_pods: List[Dict[str, Any]],
    cap_map: Dict[str, str],
) -> Dict[str, int]:
    """
    Count how many pods belonging to this workload are on each capacity type.
    Returns {"spot": N, "on-demand": N, "unknown": N}.
    """
    counts: Dict[str, int] = {"spot": 0, "on-demand": 0, "unknown": 0}
    for pod in live_pods:
        if (pod.get("namespace") or "") != namespace:
            continue
        if _get_controller_name(pod) != controller_name:
            continue
        node = pod.get("node_name")
        if not node:
            counts["unknown"] += 1
            continue
        cap = cap_map.get(node)
        if cap in ("spot", "on-demand"):
            counts[cap] += 1
        else:
            counts["unknown"] += 1
    return counts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_targets(
    classifications: List[Dict[str, Any]],
    live_pods: List[Dict[str, Any]],
    live_nodes: List[Dict[str, Any]],
) -> List[PlacementTarget]:
    """
    Translate WIE WorkloadClassification dicts into PlacementTarget objects.

    Parameters
    ----------
    classifications : list of serialized WorkloadClassification dicts
        (output of serialize_classification() or equivalent).
    live_pods : list of live pod dicts from cluster.
        Each must have: pod_name, namespace, node_name (or None if pending).
        Optional: controller_name / workload_name for faster matching.
    live_nodes : list of live node dicts from cluster.
        Each must have: node_name, capacity_type ("spot" | "on-demand").

    Returns
    -------
    List[PlacementTarget] — one entry per classification.
    action_required=False entries should be skipped by PPE.
    """
    cap_map = _build_node_capacity_map(live_nodes)
    targets: List[PlacementTarget] = []

    for cls in classifications:
        ns          = cls.get("namespace") or ""
        ctrl_name   = cls.get("controller_name") or cls.get("workload_name") or ""
        ctrl_kind   = cls.get("controller_kind") or "unknown"
        wclass      = cls.get("workload_class") or "mixed"
        od_target   = int(cls.get("min_on_demand_replicas") or 0)
        spot_target = int(cls.get("max_spot_replicas") or 0)
        total       = int(cls.get("total_replicas") or cls.get("replicas") or 0)
        signals: List[str] = []

        # Count current live distribution
        counts = _count_pod_capacity_types(ns, ctrl_name, live_pods, cap_map)
        cur_od      = counts["on-demand"]
        cur_spot    = counts["spot"]
        cur_unknown = counts["unknown"]

        # Unknown pods are treated as OD conservatively (safer to assume OD)
        cur_od += cur_unknown
        if cur_unknown:
            signals.append(f"unknown_cap_type_treated_as_od:{cur_unknown}")

        delta_od   = od_target   - cur_od
        delta_spot = spot_target - cur_spot

        # Action required only when either delta is non-zero
        action = (delta_od != 0 or delta_spot != 0)

        if not action:
            signals.append("already_at_target")
        else:
            if delta_od > 0:
                signals.append(f"need_more_od:+{delta_od}")
            if delta_od < 0:
                signals.append(f"excess_od:{delta_od}")
            if delta_spot > 0:
                signals.append(f"need_more_spot:+{delta_spot}")
            if delta_spot < 0:
                signals.append(f"excess_spot:{delta_spot}")

        logger.debug(
            "target_builder.target",
            workload=f"{ns}/{ctrl_name}",
            wclass=wclass,
            od_target=od_target,
            spot_target=spot_target,
            cur_od=cur_od,
            cur_spot=cur_spot,
            delta_od=delta_od,
            delta_spot=delta_spot,
            action_required=action,
        )

        targets.append(PlacementTarget(
            namespace=ns,
            controller_name=ctrl_name,
            controller_kind=ctrl_kind,
            workload_class=wclass,
            od_target=od_target,
            spot_target=spot_target,
            total_replicas=total,
            current_od_count=cur_od,
            current_spot_count=cur_spot,
            current_unknown_count=cur_unknown,
            delta_od=delta_od,
            delta_spot=delta_spot,
            action_required=action,
            signals=signals,
        ))

    return targets


def filter_actionable(targets: List[PlacementTarget]) -> List[PlacementTarget]:
    """Return only targets that require PPE work."""
    return [t for t in targets if t.action_required]
