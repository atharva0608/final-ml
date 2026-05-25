"""
Pod Placement Engine — 5-Layer Plan Materialization
====================================================
Sits between PlacementAdvisor (produces counts) and PlacementController
(executes evictions). Converts target counts → a fully validated, costed,
anchor-aware placement plan.

5-Layer Pipeline (plan.md spec):
    Input (pods, nodes, wie, targets, anchor_settings)
       │
       ▼ Layer 1 — StateGuard      → freshness gate, no-op detection, PROCEED|NO_OP|ABORT
       ▼ Layer 2 — AnchorPlanner   → anchor_nodes, locked_pods, anchor_map (before PodSelector)
       ▼           PodSelector     → classify + score (skips locked/system pods)
       ▼           StabilityOptimizer → minimize churn, cooldown + anchor guard
       ▼           AZDistributor   → ensure multi-AZ spread
       ▼           CapacityPlanner → sum CPU/memory, keep/provision/drain plan (never drains anchors)
       ▼ Layer 3 — BinPacker       → multi-dim BFD with anchor-first + hotspot penalty
       ▼ Layer 4 — CostProjector   → baseline + projected cost, spot% (pass 1)
       ▼ Layer 5 — PlanValidator   → PDB, IP, max_pods, storage-AZ, AZ-spread checks
       ▼           CostProjector   → finalized cost after blocked_pods removed (pass 2)
       │
       ▼
    Output (pod_assignment, movement_plan, node_plan, anchor_plan,
            cost_projection, validation_errors, az_distribution, feasibility)

This module is pure-function — no Redis/DB writes inside submodules.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

# Default cluster batch size — caps concurrent moves per cycle.
DEFAULT_BATCH_SIZE = 5

# K8s default pod-per-node limit
K8S_MAX_PODS_PER_NODE = 110

# System namespaces — never touched by the engine
DEFAULT_SYSTEM_NAMESPACES = frozenset({
    "kube-system", "kube-public", "kube-node-lease",
    "karpenter", "spot-optimizer", "cert-manager", "monitoring",
    "istio-system", "linkerd", "observability", "logging", "kube-flannel",
})

# App types that imply data-flush risk on eviction (added cost)
DB_RISK_APP_TYPES = frozenset({
    "postgresql", "mysql", "mongodb", "elasticsearch", "cassandra",
    "etcd", "zookeeper", "redis", "kafka",
})

# Hard cap on concurrent pod movements per engine cycle (movement budget).
# Prevents mass-eviction cascades independent of PDB/batch calculations.
MAX_MOVES_PER_CYCLE = 10

# Pod/node data older than this (seconds) is considered stale — engine returns a no-op
# rather than acting on ghost-node data.
DATA_FRESHNESS_THRESHOLD_SECONDS = 300  # agent reports every ~60-90s; 30s was too strict


class NodeOverheadProfiler:
    """
    Computes per-node effective schedulable capacity (plan.md Layer 2).

    Subtracts from allocatable resources:
      - DaemonSet pod CPU/memory requests (aws-node, kube-proxy, logging agents, etc.)
      - kube-reserved CPU/memory (from cluster config or sensible defaults)
      - eviction buffer memory (prevents OOM-kill cascades)
      - safety margin (configurable %, prevents packing right up to the edge)

    Output feeds bin-packing so it sizes replacement nodes honestly.
    """

    _KUBE_RESERVED_CPU_MC  = 100   # millicores
    _KUBE_RESERVED_MEM_MB  = 256   # MiB
    _EVICTION_BUFFER_MB    = 100   # MiB
    _SAFETY_CPU_PCT        = 0.10  # 10% CPU headroom
    _SAFETY_MEM_PCT        = 0.05  # 5%  memory headroom

    _DAEMONSET_OWNERS = frozenset({
        "aws-node", "kube-proxy", "node-exporter", "fluent-bit",
        "datadog-agent", "aws-otel-collector", "cni-metrics-helper",
        "calico-node", "cilium", "filebeat", "promtail",
    })

    @classmethod
    def is_daemonset_pod(cls, pod: Dict[str, Any]) -> bool:
        """True if this pod belongs to a DaemonSet.
        Primary check: controller_kind field (authoritative).
        Fallback: name-prefix heuristic for pods where controller_kind is missing.
        """
        ctrl_kind = (pod.get("controller_kind") or "").lower()
        if ctrl_kind == "daemonset":
            return True
        wclass = (pod.get("workload_class") or "").lower()
        if wclass == "system":
            return True
        owner = (pod.get("owner_name") or pod.get("controlled_by") or "").lower()
        name  = (pod.get("pod_name") or "").lower()
        return any(ds in owner or name.startswith(ds) for ds in cls._DAEMONSET_OWNERS)

    @classmethod
    def profile(
        cls,
        allocatable_cpu_mc: float,
        allocatable_mem_bytes: float,
        daemonset_pods: Optional[List[Dict[str, Any]]] = None,
        cluster_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Returns effective capacity dict:
          effective_cpu_mc      — millicores available for workload pods
          effective_mem_bytes   — bytes available for workload pods
          overhead_detail       — breakdown for UI economics panel
        """
        cfg = cluster_config or {}
        kube_cpu  = float(cfg.get("kube_reserved_cpu_mc",  cls._KUBE_RESERVED_CPU_MC))
        kube_mem  = float(cfg.get("kube_reserved_mem_mb",  cls._KUBE_RESERVED_MEM_MB)) * 1024 * 1024
        evict_buf = float(cfg.get("eviction_threshold_mb", cls._EVICTION_BUFFER_MB))   * 1024 * 1024

        ds_cpu = 0.0
        ds_mem = 0.0
        for pod in (daemonset_pods or []):
            ds_cpu += float(pod.get("cpu_request_millicores", 0))
            ds_mem += float(pod.get("memory_request_bytes",   0))

        safety_cpu = allocatable_cpu_mc    * cls._SAFETY_CPU_PCT
        safety_mem = allocatable_mem_bytes * cls._SAFETY_MEM_PCT

        eff_cpu = max(0.0, allocatable_cpu_mc    - kube_cpu  - ds_cpu - safety_cpu)
        eff_mem = max(0.0, allocatable_mem_bytes - kube_mem  - ds_mem - evict_buf - safety_mem)

        return {
            "effective_cpu_mc":    round(eff_cpu, 1),
            "effective_mem_bytes": round(eff_mem, 0),
            "overhead_detail": {
                "kube_reserved_cpu_mc":      kube_cpu,
                "kube_reserved_mem_bytes":   kube_mem,
                "daemonset_cpu_mc":          ds_cpu,
                "daemonset_mem_bytes":       ds_mem,
                "safety_margin_cpu_mc":      round(safety_cpu, 1),
                "safety_margin_mem_bytes":   round(safety_mem, 0),
                "eviction_buffer_bytes":     evict_buf,
            },
        }


def is_system_pod(pod: Dict[str, Any]) -> bool:
    """Return True if this pod must never be touched by the placement engine.

    Centralised check used by ALL submodules — do not inline this logic elsewhere.
    Checks (in order):
    1. System namespace (kube-system, etc.)
    2. controller_kind == DaemonSet (case-insensitive)
    3. workload_class == 'system' (set by WIE for DS and control-plane workloads)
    """
    ns = pod.get("namespace") or ""
    ctrl_kind = (pod.get("controller_kind") or "").lower()
    wclass = (pod.get("workload_class") or "").lower()
    return (
        ns in DEFAULT_SYSTEM_NAMESPACES
        or ctrl_kind == "daemonset"
        or wclass == "system"
    )


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PodAssignment:
    pod_name: str
    namespace: str
    current_node: Optional[str]
    current_az: Optional[str]
    current_capacity_type: Optional[str]
    target_node: Optional[str]
    target_az: Optional[str]
    target_capacity_type: str
    movement_required: bool


@dataclass
class MovementStep:
    step: int
    pod_name: str
    namespace: str
    workload_id: Optional[str]
    from_node: Optional[str]
    from_az: Optional[str]
    from_capacity_type: Optional[str]
    to_capacity_type: str
    to_az: Optional[str]
    to_node: Optional[str]          # real node name when target is an existing node; else None
    to_virtual_node: Optional[str]  # synthetic virtual_node_id when target is a provision node; else None
    reason: str
    movement_cost: float
    cpu_request_millicores: Optional[float] = None
    memory_request_bytes: Optional[float] = None
    blocked_by: Optional[str] = None


@dataclass
class NodePlanEntry:
    action: str  # keep | provision | drain
    node_name: Optional[str]         # real Kubernetes node name for keep/drain; internal planner ID for provision
    virtual_node_id: Optional[str]   # stable synthetic identity for provision entries only (e.g. "prov-spot-ap-south-1a-001"); None for keep/drain
    capacity_type: str
    az: Optional[str]
    instance_type: Optional[str] = None
    required_cpu_millicores: float = 0.0
    required_memory_bytes: float = 0.0
    pod_count: int = 0
    reason: Optional[str] = None
    # GAP 2: packed_pods carries the exact pod dicts assigned to this node so
    # InstanceSelectionService._split_provision_entry() can partition by real
    # pod groups rather than arithmetic approximation.
    packed_pods: Optional[List[Dict[str, Any]]] = None


@dataclass
class Feasibility:
    feasible: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class PlacementPlan:
    schema_version: str
    pod_assignment: Dict[str, List[Dict[str, Any]]]
    movement_plan: List[Dict[str, Any]]
    node_plan: List[Dict[str, Any]]
    node_layout: Dict[str, Any]
    az_distribution: Dict[str, Dict[str, int]]
    feasibility: Dict[str, Any]
    anchor_plan: Dict[str, Any] = field(default_factory=dict)
    cost_projection: Dict[str, Any] = field(default_factory=dict)
    validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    spot_migration_decision: Dict[str, Any] = field(default_factory=dict)
    # spot_migration_decision schema:
    # {
    #   "selected": bool,           True if spot moves or spot provisions were planned
    #   "reason": str,              machine-readable reason code
    #   "wie_eligible_spot": int,   max_spot_replicas from WIE
    #   "planner_spot_target": int, spot_target passed to PPE
    #   "confidence_gate": str,     WIE confidence_state
    #   "spot_moves_planned": int,  number of spot movement steps in the plan
    # }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pod_assignment": self.pod_assignment,
            "movement_plan": self.movement_plan,
            "node_plan": self.node_plan,
            "node_layout": self.node_layout,
            "az_distribution": self.az_distribution,
            "feasibility": self.feasibility,
            "anchor_plan": self.anchor_plan,
            "cost_projection": self.cost_projection,
            "validation_errors": self.validation_errors,
            "spot_migration_decision": self.spot_migration_decision,
        }


# ---------------------------------------------------------------------------
# Layer 1 — StateGuard
# ---------------------------------------------------------------------------

class StateGuard:
    """
    Gatekeeper — runs before ANY planning work.
    Checks cluster state, data freshness, and detects no-op (current == desired).

    Decision values:
        PROCEED  — all gates passed, engine may proceed
        NO_OP    — current state matches desired hash, skip engine entirely
        ABORT    — cluster not idle or data is stale, do not plan
    """

    PROCEED = "PROCEED"
    NO_OP = "NO_OP"
    ABORT = "ABORT"

    @staticmethod
    def _state_hash(pods: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> str:
        """Order-independent sha256 (first 16 chars) of pod→node assignments + node capacities."""
        pod_parts = sorted(
            f"{p.get('pod_name', '')}:{p.get('node_name', '')}"
            for p in pods
        )
        node_parts = sorted(
            f"{n.get('node_name', '')}:{n.get('allocatable_cpu_millicores', 0)}"
            for n in nodes
        )
        raw = "|".join(pod_parts + node_parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def check(
        pods: List[Dict[str, Any]],
        nodes: List[Dict[str, Any]],
        data_age_seconds: Optional[float] = None,
        desired_hash: Optional[str] = None,
        cluster_state: str = "idle",
    ) -> Dict[str, Any]:
        """
        Returns {"decision": PROCEED|NO_OP|ABORT, "reason": str, "current_hash": str|None}

        Step 1 — ClusterState: if not IDLE → ABORT
        Step 2 — Freshness:    if data_age > threshold → ABORT
        Step 3 — NO-OP:        if current_hash == desired_hash → NO_OP
        Step 4 — PROCEED
        """
        # Step 1 — ClusterState check
        if (cluster_state or "").lower() not in ("idle", ""):
            return {
                "decision": StateGuard.ABORT,
                "reason": f"cluster_state is '{cluster_state}', expected IDLE",
                "current_hash": None,
            }

        # Step 2 — Freshness check
        if data_age_seconds is not None and data_age_seconds > DATA_FRESHNESS_THRESHOLD_SECONDS:
            return {
                "decision": StateGuard.ABORT,
                "reason": (
                    f"stale state, age={data_age_seconds:.0f}s "
                    f"> threshold {DATA_FRESHNESS_THRESHOLD_SECONDS}s"
                ),
                "current_hash": None,
            }

        # Step 3 — NO-OP detection
        current_hash = StateGuard._state_hash(pods, nodes)
        if desired_hash and current_hash == desired_hash:
            return {
                "decision": StateGuard.NO_OP,
                "reason": "current_hash == desired_hash — system already at desired state",
                "current_hash": current_hash,
            }

        # Step 4 — PROCEED
        return {
            "decision": StateGuard.PROCEED,
            "reason": "all guards passed",
            "current_hash": current_hash,
        }


# ---------------------------------------------------------------------------
# Layer 2 — AnchorPlanner  (runs BEFORE PodSelector)
# ---------------------------------------------------------------------------

class AnchorPlanner:
    """
    Select anchor nodes and lock critical pods onto them.
    Anchor nodes are never drained; their pods are excluded from all movement lists.
    Runs before PodSelector so locked_pods can be passed forward.

    Hard constraint: anchor nodes MUST be on-demand nodes. Spot nodes are preemptible
    and cannot guarantee the stability that anchoring requires. The engine only falls
    back to spot anchor nodes if the cluster has zero on-demand nodes, and logs a
    warning in that case.

    anchor_settings = {
        "min_anchor_nodes":        int   (0 — disabled),
        "preferred_capacity_type": str   ("on-demand" [default] | "spot" | "any")
                                         NOTE: "spot" and "any" are overridden by the
                                         hard OD-first filter — spot nodes are excluded
                                         from the candidate pool unless no OD nodes exist.
        "az_spread_required":      bool,
    }
    """

    @staticmethod
    def select(
        nodes: List[Dict[str, Any]],
        pods: List[Dict[str, Any]],
        wie: Dict[str, Any],
        anchor_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns {
            "anchor_nodes": set[str],
            "locked_pods":  set[str],
            "anchor_count": int,
            "anchor_map":   dict[str, str],  # pod_name → anchor_node_name
            "warnings":     List[str],
        }
        """
        warnings: List[str] = []
        min_user = int(anchor_settings.get("min_anchor_nodes") or 0)
        # Anchor nodes must be on-demand — spot nodes can be interrupted at any moment,
        # making them unsuitable as stable anchors for critical pods.
        # preferred_cap defaults to "on-demand" (not "any") to enforce this constraint.
        preferred_cap = (anchor_settings.get("preferred_capacity_type") or "on-demand").lower()
        az_spread = bool(
            anchor_settings.get("az_spread_required") or wie.get("az_spread_required")
        )

        tier = (wie.get("tier") or "").lower()
        data_safety = (wie.get("data_safety") or "").upper()
        disruption_safe = wie.get("disruption_safe", True)
        is_critical_workload = (
            tier in ("platinum", "gold")
            or data_safety == "STATEFUL"
            or disruption_safe is False
        )

        # WIE app type used for pod-level DB check
        _wie_app_type = (
            wie.get("classifier_app_type") or wie.get("detected_app_type") or ""
        ).lower()
        _DB_TYPES = frozenset({
            "redis", "postgres", "postgresql", "mysql", "mariadb",
            "mongodb", "mongo", "elasticsearch", "kafka", "zookeeper",
            "cassandra", "etcd", "memcached",
        })

        # Count pods per owner to detect singletons (only replica → guaranteed downtime on eviction)
        from collections import Counter as _Counter
        _owner_counts = _Counter(
            p.get("owner_name") or p.get("pod_name", "")
            for p in pods if not is_system_pod(p)
        )

        def _is_pod_level_critical(p: Dict[str, Any]) -> bool:
            """
            True when the pod itself requires an OD anchor regardless of workload tier.
            Mirrors PodSelector._is_spot_disqualified pod-level criteria:
              - Singleton: only one replica — eviction causes guaranteed downtime.
              - Primary/leader: StatefulSet ordinal-0 or role=primary/master/leader label.
              - PVC-backed: has persistent storage — must not be preempted.
              - DB app type: data-store risk even without tier classification.
            """
            # Singleton
            owner = p.get("owner_name") or p.get("pod_name", "")
            if _owner_counts.get(owner, 0) <= 1:
                return True
            # PVC-backed
            if p.get("has_pvc") or p.get("persistent_volume_claims"):
                return True
            # Primary / leader pod by ordinal or label
            pod_name = (p.get("pod_name") or "").rstrip()
            if pod_name.endswith("-0"):
                return True
            labels = p.get("labels") or {}
            if labels.get("role") in ("primary", "master", "leader"):
                return True
            sts_label = labels.get("statefulset.kubernetes.io/pod-name", "")
            if sts_label.endswith("-0"):
                return True
            # DB / data-store
            if any(t in _wie_app_type for t in _DB_TYPES):
                return True
            if (wie.get("workload_class") or "").lower() == "db":
                return True
            return False

        # Identify critical (non-system) pods — workload-level OR pod-level critical
        critical_pods_list = [
            p for p in pods
            if not is_system_pod(p) and (is_critical_workload or _is_pod_level_critical(p))
        ]

        # Step 1 — Determine anchor count from three floors + 50% safety cap
        # min_capacity: how many nodes needed to cover critical pod CPU
        avg_node_cpu = 0.0
        if nodes:
            avg_node_cpu = sum(
                float(n.get("allocatable_cpu_millicores") or 0) for n in nodes
            ) / len(nodes)
        critical_cpu_total = sum(
            float(p.get("cpu_request_millicores") or 0) for p in critical_pods_list
        )
        min_capacity = math.ceil(critical_cpu_total / avg_node_cpu) if avg_node_cpu > 0 else 0
        min_ha = 2 if az_spread else 1
        anchor_count = max(min_user, min_capacity, min_ha)
        # Safety cap: anchors must not exceed 50% of cluster
        max_anchors = max(1, math.ceil(len(nodes) * 0.5))
        anchor_count = min(anchor_count, max_anchors)

        if anchor_count == 0:
            return {
                "anchor_nodes": set(), "locked_pods": set(),
                "anchor_count": 0, "anchor_map": {}, "warnings": [],
            }

        # Nodes that host critical pods score highest
        critical_pod_nodes: set = set()
        for p in critical_pods_list:
            node = p.get("node_name")
            if node:
                critical_pod_nodes.add(node)

        def _is_od(n: Dict[str, Any]) -> bool:
            cap = (n.get("capacity_type") or "").lower()
            return cap in ("on-demand", "ondemand", "on_demand")

        def _score(n: Dict[str, Any]) -> float:
            name = n.get("node_name") or ""
            alloc_cpu = float(n.get("allocatable_cpu_millicores") or 1)
            used_cpu = float(n.get("used_cpu_millicores") or 0)
            util = used_cpu / alloc_cpu if alloc_cpu > 0 else 1.0
            s = 0.0
            s += len([p for p in critical_pods_list if p.get("node_name") == name]) * 10.0
            s -= util  # lower utilisation is better
            # Bug 4 fix: strongly prefer nodes that currently host pods over empty nodes.
            # An empty node has pod_count=0 → no bonus. A busy node gets +2 minimum.
            # This prevents a zero-pod node from tying with or beating occupied nodes.
            pod_count = int(n.get("pod_count") or 0)
            s += min(pod_count, 20) * 0.2  # cap contribution at 20 pods (score +4 max)
            return s

        all_candidates = [n for n in nodes if n.get("node_name")]

        # Hard rule: anchor nodes MUST be on-demand. Spot nodes are preemptible and
        # cannot provide the stability guarantee that anchoring requires.
        # Only fall back to spot if the cluster has NO on-demand nodes at all.
        od_candidates = [n for n in all_candidates if _is_od(n)]
        if od_candidates:
            candidates = od_candidates
        else:
            warnings.append(
                "anchor_fallback_to_spot: no on-demand nodes found — "
                "anchor nodes will be spot (reduced stability guarantee)"
            )
            candidates = all_candidates

        candidates.sort(key=_score, reverse=True)

        # Step 4 — AZ-spread selection
        anchor_nodes: set = set()
        az_seen: set = set()
        all_azs = {n.get("az") for n in candidates if n.get("az")}
        total_azs = len(all_azs) or 1
        from collections import defaultdict as _defaultdict
        az_counts: Dict[str, int] = _defaultdict(int)

        for n in candidates:
            if len(anchor_nodes) >= anchor_count:
                break
            az = n.get("az") or "unknown"
            az_quota = math.ceil(anchor_count / total_azs)
            if az_spread and az_counts[az] >= az_quota and len(az_seen) < total_azs:
                continue
            anchor_nodes.add(n["node_name"])
            az_seen.add(az)
            az_counts[az] += 1

        if az_spread and len(az_seen) < 2 and len(anchor_nodes) > 0:
            warnings.append(
                f"az_spread_required but anchor nodes span only {len(az_seen)} AZ(s)"
            )
        if len(anchor_nodes) < anchor_count:
            warnings.append(
                f"could only select {len(anchor_nodes)} anchor nodes (requested {anchor_count})"
            )

        # Bug 4 fix: Post-selection purge — remove anchors that have zero current pods
        # and whose AZ is already covered by another anchor with actual pods.
        # This prevents empty nodes (like ip-192-168-34-200) from being permanently
        # anchored just because they have low utilisation.
        _anchor_node_map = {n["node_name"]: n for n in nodes if n.get("node_name") in anchor_nodes}
        _az_covered_by_nonempty: set = set()
        _empty_anchors: List[str] = []
        for _aname in list(anchor_nodes):
            _anode = _anchor_node_map.get(_aname, {})
            _apods = int(_anode.get("pod_count") or 0)
            _aaz = _anode.get("az") or "unknown"
            _has_critical = any(p.get("node_name") == _aname for p in critical_pods_list)
            if _apods > 0 or _has_critical:
                _az_covered_by_nonempty.add(_aaz)
            else:
                _empty_anchors.append(_aname)
        for _aname in _empty_anchors:
            _anode = _anchor_node_map.get(_aname, {})
            _aaz = _anode.get("az") or "unknown"
            if _aaz in _az_covered_by_nonempty:
                # AZ is already covered by a non-empty anchor — safe to drop this one
                anchor_nodes.discard(_aname)
                warnings.append(
                    f"anchor_pruned_empty_node: {_aname} removed from anchor set "
                    f"(0 pods, AZ {_aaz} already covered by another anchor)"
                )

        # Step 5 — Assign critical pods to anchor nodes (build anchor_map)
        anchor_map: Dict[str, str] = {}
        anchor_node_objects = [n for n in nodes if n.get("node_name") in anchor_nodes]
        for p in critical_pods_list:
            pod_name = p.get("pod_name")
            if not pod_name:
                continue
            current_node = p.get("node_name")
            if current_node in anchor_nodes:
                anchor_map[pod_name] = current_node
                continue
            if anchor_node_objects:
                pod_az = p.get("az")
                best = min(
                    anchor_node_objects,
                    key=lambda n: (
                        (n.get("az") or "") != (pod_az or ""),
                        float(n.get("used_cpu_millicores") or 0)
                        / max(float(n.get("allocatable_cpu_millicores") or 1), 1),
                    ),
                )
                anchor_map[pod_name] = best["node_name"]

        # Lock only critical pods that are CURRENTLY sitting on an anchor node.
        # Pods on non-anchor nodes remain free to move (to spot or to an anchor via BinPacker).
        # Locking every entry in anchor_map would freeze pods that haven't yet reached
        # their anchor — preventing the engine from placing them correctly.
        locked_pods: set = {
            p.get("pod_name")
            for p in critical_pods_list
            if p.get("pod_name") and p.get("node_name") in anchor_nodes
        }

        return {
            "anchor_nodes": anchor_nodes,
            "locked_pods": locked_pods,
            "anchor_count": len(anchor_nodes),
            "anchor_map": anchor_map,
            "warnings": warnings,
        }


from backend.services.stateful_intelligence import StatefulIntelligence

# ---------------------------------------------------------------------------
# Submodule A — PodSelector
# ---------------------------------------------------------------------------

class PodSelector:
    """Classify pods, score movement cost, pick candidates for spot/OD."""

    # App types whose pods must never land on spot (data-flush risk)
    _SPOT_BLOCK_APP_TYPES: frozenset = frozenset({
        "redis", "postgres", "postgresql", "mysql", "mariadb",
        "mongodb", "mongo", "elasticsearch", "kafka", "zookeeper",
        "cassandra", "etcd", "memcached",
    })

    @staticmethod
    def _is_spot_disqualified(
        p: Dict[str, Any],
        wie: Dict[str, Any],
        total_replicas: int,
    ) -> tuple:
        """
        Returns (disqualified: bool, reason: str).
        Conservative — when in doubt, assign to OD.
        """
        # PVC: pod has persistent storage — never evict to spot
        if p.get("has_pvc") or p.get("persistent_volume_claims"):
            return True, "has_pvc"

        # Singleton: only one replica — eviction causes guaranteed downtime
        if total_replicas <= 1:
            return True, "singleton"

        # Primary / leader pod: StatefulSet pod-0 or role=primary/master label
        pod_name = (p.get("pod_name") or "").rstrip()
        if pod_name.endswith("-0"):
            return True, "primary_pod_ordinal_0"
        labels = p.get("labels") or {}
        if labels.get("role") in ("primary", "master", "leader"):
            return True, f"primary_label:role={labels.get('role')}"
        # StatefulSet pod-name label ending in -0
        sts_pod_name = labels.get("statefulset.kubernetes.io/pod-name", "")
        if sts_pod_name.endswith("-0"):
            return True, "primary_sts_pod_name"

        # DB/data-store workload type from WIE
        wie_app_type = (wie.get("classifier_app_type") or wie.get("detected_app_type") or "").lower()
        if any(t in wie_app_type for t in PodSelector._SPOT_BLOCK_APP_TYPES):
            return True, f"db_app_type:{wie_app_type}"
        if wie.get("workload_class") == "db":
            return True, "workload_class:db"

        # High restart count — unstable pod, don't move to spot
        restart_count = p.get("restart_count") or p.get("restarts") or 0
        if isinstance(restart_count, (int, float)) and restart_count > 3:
            return True, f"high_restarts:{restart_count}"

        return False, ""

    @staticmethod
    def classify_and_score(
        pods: List[Dict[str, Any]],
        wie: Dict[str, Any],
        targets: Dict[str, Any],
        locked_pods: Optional[set] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns dict with 4 lists of pods enriched with classification + cost:
            to_move_to_spot      — excess on-demand → spot
            to_move_to_ondemand  — excess spot      → on-demand
            stay_put             — already at target
            system_skip          — never touched (system pods + anchor-locked pods)
        """
        ondemand_target = int(targets.get("ondemand_target") or 0)
        spot_target = int(targets.get("spot_target") or 0)
        total_replicas = ondemand_target + spot_target
        wie_app_type = (wie.get("classifier_app_type") or wie.get("detected_app_type") or "").lower()
        locked_pods = locked_pods or set()

        system_skip: List[Dict[str, Any]] = []
        spot_now: List[Dict[str, Any]] = []
        ondemand_now: List[Dict[str, Any]] = []
        # Pods forcibly assigned to OD regardless of their current capacity type
        forced_od: List[Dict[str, Any]] = []

        for p in pods:
            cap = (p.get("capacity_type") or "unknown").lower()

            # Centralised system-pod check (DaemonSets, kube-system, etc.)
            if is_system_pod(p):
                system_skip.append({**p, "movement_cost": None, "reason": "system_or_daemonset"})
                continue

            # Anchor-locked pods: excluded from movement, treated as stay_put
            if p.get("pod_name") in locked_pods:
                system_skip.append({**p, "movement_cost": None, "reason": "anchor_locked"})
                continue

            cost = PodSelector._movement_cost(p, wie, wie_app_type)
            entry = {**p, "movement_cost": cost}

            # Per-pod spot safety check — disqualified pods are forced to OD
            disq, disq_reason = PodSelector._is_spot_disqualified(p, wie, total_replicas)
            if disq:
                forced_od.append({**entry, "spot_disqualified": True, "disqualified_reason": disq_reason})
                continue

            if cap == "spot":
                spot_now.append(entry)
            else:
                # treat 'unknown' / 'on-demand' / missing → on-demand bucket
                ondemand_now.append(entry)

        # forced_od pods reduce the effective spot target — adjust OD target up
        od_target_eff = ondemand_target + len(forced_od)
        spot_target_eff = max(0, spot_target - len(forced_od))
        if forced_od:
            logger.debug(
                "PodSelector: %d pods forcibly assigned to OD (spot_target adjusted %d→%d)",
                len(forced_od), spot_target, spot_target_eff,
            )

        # Decide deltas — forced_od pods are treated as OD-anchored (don't move to spot)
        excess_ondemand = max(0, len(ondemand_now) - od_target_eff)
        excess_spot = max(0, len(spot_now) - spot_target_eff)

        # Cheapest non-forced pods move first
        ondemand_now.sort(key=lambda x: x["movement_cost"])
        spot_now.sort(key=lambda x: x["movement_cost"])

        to_move_to_spot = ondemand_now[:excess_ondemand]
        stay_ondemand = ondemand_now[excess_ondemand:]

        to_move_to_ondemand = spot_now[:excess_spot]
        stay_spot = spot_now[excess_spot:]

        return {
            "to_move_to_spot": to_move_to_spot,
            "to_move_to_ondemand": to_move_to_ondemand,
            "stay_put": stay_ondemand + stay_spot + forced_od,
            "system_skip": system_skip,
        }

    @staticmethod
    def _movement_cost(p: Dict[str, Any], wie: Dict[str, Any], app_type: str) -> float:
        """Lower cost = cheaper to move."""
        cost = 0.0
        age = p.get("age_seconds")
        ready = p.get("ready", True)

        # Recently scheduled → expensive to bounce again
        if age is not None and age < 600:
            cost += 0.5
        # Long-running pods are usually safe to bounce
        if age is not None and age > 86400:
            cost -= 0.2
        # Not ready yet (still warming up)
        if not ready:
            cost += 0.3
        # Database-like apps carry data flush risk
        if any(t in app_type for t in DB_RISK_APP_TYPES):
            cost += 0.2
            # Use specialized plugin to check priority
            _si = StatefulIntelligence(cluster_id="") # cluster_id not available here easily, use empty
            _matched_type = next((t for t in DB_RISK_APP_TYPES if t in app_type), None)
            if _matched_type:
                priority = _si.get_movement_priority(_matched_type)
                if priority == 1: # High risk
                    cost += 0.5
        # Stateful WIE classification raises cost too
        if (wie.get("data_safety") or "").upper() == "STATEFUL":
            cost += 0.3
        # WIE spot_score tilts cheapness in spot's favor
        wie_ss = wie.get("spot_score")
        if isinstance(wie_ss, (int, float)):
            cost -= 0.05 * (wie_ss - 5)  # spot_score 5 = neutral, 10 = -0.25

        return round(cost, 3)


# ---------------------------------------------------------------------------
# Submodule B — StabilityOptimizer
# ---------------------------------------------------------------------------

class StabilityOptimizer:
    """Minimize movements, protect critical pods, respect PDB margin."""

    @staticmethod
    def filter(
        selected: Dict[str, List[Dict[str, Any]]],
        wie: Dict[str, Any],
        targets: Dict[str, Any],
        in_flight_evictions: int = 0,
        cordoned_nodes: Optional[set] = None,
        cooldown_pods: Optional[set] = None,
        anchor_nodes: Optional[set] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        """
        Returns (filtered_selected, warnings).
        Pods rejected get `blocked_by` populated and are dropped from movement lists.
        """
        warnings: List[str] = []
        cordoned_nodes = cordoned_nodes or set()
        cooldown_pods = cooldown_pods or set()
        anchor_nodes = anchor_nodes or set()

        # Hard rule 1: disruption_safe == False → no moves at all
        if wie.get("disruption_safe") is False:
            warnings.append("disruption_safe=false — skipping all moves this cycle")
            return {
                "to_move_to_spot": [],
                "to_move_to_ondemand": [],
                "stay_put": (
                    selected.get("stay_put", [])
                    + selected.get("to_move_to_spot", [])
                    + selected.get("to_move_to_ondemand", [])
                ),
                "system_skip": selected.get("system_skip", []),
            }, warnings

        # Hard rule 3: tier-based protection
        tier = (wie.get("tier") or "").lower()
        spot_friendly = wie.get("spot_friendly")
        if tier == "platinum":
            warnings.append("tier=Platinum — all moves blocked")
            return {
                "to_move_to_spot": [],
                "to_move_to_ondemand": [],
                "stay_put": (
                    selected.get("stay_put", [])
                    + selected.get("to_move_to_spot", [])
                    + selected.get("to_move_to_ondemand", [])
                ),
                "system_skip": selected.get("system_skip", []),
            }, warnings

        # Soft optimization: trivial deltas → emit no moves
        ondemand_target = int(targets.get("ondemand_target") or 0)
        spot_target = int(targets.get("spot_target") or 0)
        observed = int(targets.get("observed_replicas") or (
            len(selected.get("to_move_to_spot", []))
            + len(selected.get("to_move_to_ondemand", []))
            + len(selected.get("stay_put", []))
        ))
        # If totals are within ±1 of targets, skip
        if observed and abs((observed - len(selected.get("system_skip", []))) - (ondemand_target + spot_target)) > 0:
            pass  # significant delta — proceed

        def _filter_list(pods: List[Dict[str, Any]], direction: str) -> List[Dict[str, Any]]:
            kept = []
            for p in pods:
                pod_name = p.get("pod_name")
                # Cooldown integration: pod recently evicted — skip silently
                if pod_name in cooldown_pods:
                    continue
                # Cordoned source node
                if p.get("node_name") in cordoned_nodes:
                    continue
                # Anchor node guard: pod lives on an anchor node — block movement
                if p.get("node_name") in anchor_nodes:
                    warnings.append(
                        f"anchor node guard — blocking move for {pod_name} on {p.get('node_name')}"
                    )
                    continue
                # Gold + not spot_friendly: block spot moves only
                if direction == "to_spot" and tier == "gold" and not spot_friendly:
                    warnings.append(f"tier=Gold,spot_friendly=false — blocking spot move for {pod_name}")
                    continue
                kept.append(p)
            return kept

        filtered_to_spot = _filter_list(selected.get("to_move_to_spot", []), "to_spot")
        filtered_to_ondemand = _filter_list(selected.get("to_move_to_ondemand", []), "to_ondemand")

        # PDB / last-pod safeguard — only enforced when ready_replicas is known
        _ready_replicas_raw = wie.get("ready_replicas")
        ready_replicas = int(_ready_replicas_raw or 0)
        pdb_min = wie.get("pdb_min_available")
        moves_total = len(filtered_to_spot) + len(filtered_to_ondemand)
        if _ready_replicas_raw is not None or pdb_min is not None:
            max_concurrent = ready_replicas - in_flight_evictions
            if pdb_min is not None:
                max_concurrent -= int(pdb_min)
            if max_concurrent < 1:
                warnings.append("PDB margin exhausted — no further moves permitted")
                return {
                    "to_move_to_spot": [],
                    "to_move_to_ondemand": [],
                    "stay_put": (
                        selected.get("stay_put", [])
                        + filtered_to_spot
                        + filtered_to_ondemand
                    ),
                    "system_skip": selected.get("system_skip", []),
                }, warnings
        else:
            max_concurrent = batch_size

        # Cap by max_concurrent and batch_size
        cap = min(batch_size, max(0, max_concurrent))
        if moves_total > cap:
            # Trim from the tail (highest cost pods first)
            combined = filtered_to_spot + filtered_to_ondemand
            combined.sort(key=lambda x: x.get("movement_cost") or 0)
            allowed = combined[:cap]
            allowed_names = {p["pod_name"] for p in allowed}
            filtered_to_spot = [p for p in filtered_to_spot if p["pod_name"] in allowed_names]
            filtered_to_ondemand = [p for p in filtered_to_ondemand if p["pod_name"] in allowed_names]
            warnings.append(f"capped moves to {cap} this cycle (PDB+batch)")

        return {
            "to_move_to_spot": filtered_to_spot,
            "to_move_to_ondemand": filtered_to_ondemand,
            "stay_put": selected.get("stay_put", []),
            "system_skip": selected.get("system_skip", []),
        }, warnings


# ---------------------------------------------------------------------------
# Submodule C — AZDistributor
# ---------------------------------------------------------------------------

class AZDistributor:
    """Assign target_az to each moved pod; enforce multi-AZ spread when required."""

    @staticmethod
    def assign(
        filtered: Dict[str, List[Dict[str, Any]]],
        nodes: List[Dict[str, Any]],
        wie: Dict[str, Any],
        targets: Dict[str, Any],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, int]], List[str]]:
        """
        Returns (filtered_with_az, az_distribution, warnings).
        Each entry in to_move_to_* gets a `target_az` assigned.
        """
        warnings: List[str] = []
        az_spread_required = bool(wie.get("az_spread_required"))

        # Collect available AZs from nodes
        all_azs = sorted({n["az"] for n in nodes if n.get("az")})
        if not all_azs:
            warnings.append("no AZ data in nodes — cannot distribute")
            for p in filtered.get("to_move_to_spot", []) + filtered.get("to_move_to_ondemand", []):
                p["target_az"] = None
            return filtered, {}, warnings

        # Current distribution from stay_put pods
        az_counts: Dict[str, Dict[str, int]] = {az: {"spot": 0, "ondemand": 0} for az in all_azs}
        for p in filtered.get("stay_put", []):
            az = p.get("az")
            if az not in az_counts:
                continue
            cap = (p.get("capacity_type") or "ondemand").lower()
            key = "spot" if cap == "spot" else "ondemand"
            az_counts[az][key] += 1

        ondemand_target = int(targets.get("ondemand_target") or 0)
        spot_target = int(targets.get("spot_target") or 0)
        num_az = len(all_azs)
        spot_per_az_cap = math.ceil(spot_target / num_az) if num_az and az_spread_required else None
        od_per_az_cap = math.ceil(ondemand_target / num_az) if num_az and az_spread_required else None

        def _pick_az(target_capacity: str) -> str:
            """Pick the AZ with the lowest count for the given capacity_type."""
            key = "spot" if target_capacity == "spot" else "ondemand"
            cap = spot_per_az_cap if target_capacity == "spot" else od_per_az_cap
            sorted_azs = sorted(all_azs, key=lambda az: az_counts[az][key])
            for az in sorted_azs:
                if cap is None or az_counts[az][key] < cap:
                    az_counts[az][key] += 1
                    return az
            # Fall back to lowest count even if cap exceeded
            chosen = sorted_azs[0]
            az_counts[chosen][key] += 1
            return chosen

        for p in filtered.get("to_move_to_spot", []):
            p["target_az"] = _pick_az("spot")
            p["target_capacity_type"] = "spot"
        for p in filtered.get("to_move_to_ondemand", []):
            p["target_az"] = _pick_az("ondemand")
            p["target_capacity_type"] = "on-demand"

        # Validate spread requirement
        if az_spread_required:
            spot_total = sum(az_counts[az]["spot"] for az in all_azs)
            spot_azs_used = sum(1 for az in all_azs if az_counts[az]["spot"] > 0)
            if spot_total >= 2 and spot_azs_used < 2:
                warnings.append("az_spread_required but spot pods collapsed to one AZ")

        az_distribution = {
            az: {**az_counts[az], "total": az_counts[az]["spot"] + az_counts[az]["ondemand"]}
            for az in all_azs
        }
        return filtered, az_distribution, warnings


# ---------------------------------------------------------------------------
# Submodule D — CapacityPlanner
# ---------------------------------------------------------------------------

class CapacityPlanner:
    """Sum CPU/memory of moved pods per (AZ, capacity_type) bucket; compute required nodes."""

    @staticmethod
    def plan(
        filtered: Dict[str, List[Dict[str, Any]]],
        nodes: List[Dict[str, Any]],
        anchor_nodes: Optional[set] = None,
        node_pod_counts: Optional[Dict[str, int]] = None,
        consolidation_mode: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Returns (node_plan, warnings).
        node_plan entries: {action: keep|provision|drain, node_name, capacity_type, az,
                            required_cpu_millicores, required_memory_bytes, pod_count}
        Anchor nodes are never emitted as drain candidates.
        """
        anchor_nodes = anchor_nodes or set()
        warnings: List[str] = []
        node_plan: List[Dict[str, Any]] = []

        # Bucket moves by (az, capacity_type)
        buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for p in filtered.get("to_move_to_spot", []) + filtered.get("to_move_to_ondemand", []):
            az = p.get("target_az") or "unknown"
            cap = p.get("target_capacity_type") or "on-demand"
            key = (az, cap)
            if key not in buckets:
                buckets[key] = {"cpu_mc": 0.0, "mem_b": 0.0, "pod_count": 0, "pods": []}
            buckets[key]["cpu_mc"] += float(p.get("cpu_request_millicores") or 0)
            buckets[key]["mem_b"] += float(p.get("memory_request_bytes") or 0)
            buckets[key]["pod_count"] += 1
            buckets[key]["pods"].append(p)

        # Index nodes by (az, capacity_type) for slack analysis
        nodes_by_bucket: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for n in nodes:
            az = n.get("az") or "unknown"
            cap = (n.get("capacity_type") or "on-demand").lower()
            cap_norm = "on-demand" if cap in ("on-demand", "ondemand") else "spot"
            nodes_by_bucket.setdefault((az, cap_norm), []).append(n)

        # 1. Existing nodes that fit pods → "keep"
        kept_nodes: set = set()
        for key, bucket in buckets.items():
            avail_nodes = nodes_by_bucket.get(key, [])
            for node in sorted(avail_nodes, key=lambda x: -(x.get("allocatable_cpu_millicores") or 0)):
                node_name = node.get("node_name")
                used_cpu = float(node.get("used_cpu_millicores") or 0)
                used_mem = float(node.get("used_memory_bytes") or 0)
                cap_cpu = float(node.get("allocatable_cpu_millicores") or 0)
                cap_mem = float(node.get("allocatable_memory_bytes") or 0)
                slack_cpu = max(0.0, cap_cpu - used_cpu)
                slack_mem = max(0.0, cap_mem - used_mem)
                # Pick pods that fit
                fit_cpu, fit_mem, fit_count = 0.0, 0.0, 0
                for p in list(bucket["pods"]):
                    pcpu = float(p.get("cpu_request_millicores") or 0)
                    pmem = float(p.get("memory_request_bytes") or 0)
                    if fit_cpu + pcpu <= slack_cpu and fit_mem + pmem <= slack_mem:
                        fit_cpu += pcpu
                        fit_mem += pmem
                        fit_count += 1
                        bucket["pods"].remove(p)
                if fit_count > 0:
                    node_plan.append({
                        "action": "keep",
                        "node_name": node_name,
                        "capacity_type": key[1],
                        "az": key[0],
                        "instance_type": node.get("instance_type"),
                        "required_cpu_millicores": fit_cpu,
                        "required_memory_bytes": fit_mem,
                        "pod_count": fit_count,
                        "retention_reason": "anchor_node" if node_name in anchor_nodes else "fits_pods",
                    })
                    kept_nodes.add(node_name)

        # 2b. Drain-reuse: before provisioning, check if a soon-to-be-empty node
        #     (drain candidate) in the same bucket can absorb leftover pods.
        #     If yes, convert it to a "keep" entry — saves a provision.
        _moving_pods = (
            filtered.get("to_move_to_spot", []) + filtered.get("to_move_to_ondemand", [])
        )
        # Pre-compute per-node leaving count
        _leaving: Dict[str, int] = {}
        for _mp in _moving_pods:
            _nname = _mp.get("node_name")
            if _nname:
                _leaving[_nname] = _leaving.get(_nname, 0) + 1

        for key, bucket in buckets.items():
            if not bucket["pods"]:
                continue
            az_b, cap_b = key
            for n in nodes:
                name = n.get("node_name")
                if not name or name in kept_nodes or name in (anchor_nodes or set()):
                    continue
                _az = n.get("az") or "unknown"
                _cap = (n.get("capacity_type") or "on-demand").lower()
                _cap = "on-demand" if _cap in ("on-demand", "ondemand") else "spot"
                if _az != az_b or _cap != cap_b:
                    continue
                # Is this node about to be fully drained?
                _count = int((node_pod_counts or {}).get(name, n.get("pod_count") or 0))
                _leaving_this = _leaving.get(name, 0)
                if not (_count > 0 and _leaving_this >= _count):
                    continue
                # Node becomes empty after moves — full capacity available
                alloc_cpu = float(n.get("allocatable_cpu_millicores") or 4000)
                alloc_mem = float(n.get("allocatable_memory_bytes") or 16e9)
                fit_cpu, fit_mem, fit_count = 0.0, 0.0, 0
                for _p in list(bucket["pods"]):
                    pcpu = float(_p.get("cpu_request_millicores") or 0)
                    pmem = float(_p.get("memory_request_bytes") or 0)
                    if fit_cpu + pcpu <= alloc_cpu and fit_mem + pmem <= alloc_mem:
                        fit_cpu += pcpu
                        fit_mem += pmem
                        fit_count += 1
                        bucket["pods"].remove(_p)
                if fit_count > 0:
                    node_plan.append({
                        "action": "keep",
                        "node_name": name,
                        "capacity_type": cap_b,
                        "az": az_b,
                        "instance_type": n.get("instance_type"),
                        "required_cpu_millicores": fit_cpu,
                        "required_memory_bytes": fit_mem,
                        "pod_count": fit_count,
                        "allocatable_cpu_millicores": alloc_cpu,
                        "allocatable_memory_bytes": alloc_mem,
                        "retention_reason": "drain_reuse",
                    })
                    kept_nodes.add(name)

        # 2. Provision new nodes for leftover pods in each bucket
        # Bug 2 fix: in consolidation_mode (spot_target=0, no new spot nodes allowed),
        # do NOT emit provision entries for spot-capacity buckets. Instead, redistribute
        # leftover spot-bucket pods onto existing on-demand keep nodes.
        # Provisioning a new spot node while consolidating OD nodes is contradictory:
        # the plan says "reduce OD nodes" while Karpenter would add spot nodes.
        for key, bucket in buckets.items():
            leftover = bucket["pods"]
            if not leftover:
                continue

            # Consolidation mode: redirect spot-bucket leftovers to OD keep-nodes
            if consolidation_mode and key[1] == "spot":
                _od_keeps = [e for e in node_plan if e.get("action") == "keep" and e.get("capacity_type") == "on-demand"]
                if _od_keeps:
                    # Distribute pods evenly across OD keep-nodes
                    for i, _p in enumerate(leftover):
                        _target = _od_keeps[i % len(_od_keeps)]
                        _target["pod_count"] = _target.get("pod_count", 0) + 1
                        _target["required_cpu_millicores"] = _target.get("required_cpu_millicores", 0) + float(_p.get("cpu_request_millicores") or 0)
                        _target["required_memory_bytes"] = _target.get("required_memory_bytes", 0) + float(_p.get("memory_request_bytes") or 0)
                    warnings.append(
                        f"consolidation_mode: {len(leftover)} pod(s) from spot bucket "
                        f"({key[0]}, spot) redistributed to OD keep-nodes — no new spot provision."
                    )
                else:
                    warnings.append(
                        f"consolidation_mode: no OD keep-nodes available to absorb "
                        f"{len(leftover)} spot-bucket pods in {key[0]}."
                    )
                continue  # skip the provision block below for this bucket
            # Pick representative instance from existing nodes in this bucket; else fallback
            rep = nodes_by_bucket.get(key, [])
            if rep:
                rep_node = max(rep, key=lambda n: (n.get("allocatable_cpu_millicores") or 0))
                inst_type = rep_node.get("instance_type")
                inst_cpu = float(rep_node.get("allocatable_cpu_millicores") or 4000)
                inst_mem = float(rep_node.get("allocatable_memory_bytes") or 16e9)
            else:
                inst_type = None
                inst_cpu = 4000.0
                inst_mem = 16e9

            need_cpu = sum(float(p.get("cpu_request_millicores") or 0) for p in leftover)
            need_mem = sum(float(p.get("memory_request_bytes") or 0) for p in leftover)
            n_for_cpu = math.ceil(need_cpu / inst_cpu) if inst_cpu > 0 else len(leftover)
            n_for_mem = math.ceil(need_mem / inst_mem) if inst_mem > 0 else len(leftover)
            required = max(1, n_for_cpu, n_for_mem)

            # GAP 2: partition pods evenly across required nodes so each
            # provision entry carries its exact assigned pod list.
            chunk = math.ceil(len(leftover) / required)
            for i in range(required):
                pod_slice = leftover[i * chunk:(i + 1) * chunk]
                slice_cpu = sum(float(p.get("cpu_request_millicores") or 0) for p in pod_slice)
                slice_mem = sum(float(p.get("memory_request_bytes")   or 0) for p in pod_slice)
                # 15% headroom — prevents OOMKill / kubelet evictions from OS overhead
                _OVERHEAD = 1.15
                _base_cpu = slice_cpu if slice_cpu else need_cpu / required
                _base_mem = slice_mem if slice_mem else need_mem / required
                # Stable synthetic ID: prov-<capacity>-<az>-<seq>.
                # Used as the BinPacker cursor key AND exposed to the UI as
                # virtual_node_id so the frontend never sees this as a real node.
                _vnode_id = f"prov-{key[1]}-{key[0]}-{i+1:03d}"
                node_plan.append({
                    "action": "provision",
                    "node_name": _vnode_id,        # internal planner cursor key
                    "virtual_node_id": _vnode_id,  # explicit typed identity field
                    "capacity_type": key[1],
                    "az": key[0],
                    "instance_type": inst_type,
                    "required_cpu_millicores": math.ceil(_base_cpu * _OVERHEAD),
                    "required_memory_bytes":   math.ceil(_base_mem * _OVERHEAD),
                    "pod_count": len(pod_slice),
                    "packed_pods": pod_slice,   # GAP 2: exact pod list
                    "allocatable_cpu_millicores": inst_cpu,
                    "allocatable_memory_bytes": inst_mem,
                })

        # 3. Drain candidates — nodes that would become empty after moves
        moved_pod_names = {
            p["pod_name"]
            for p in filtered.get("to_move_to_spot", []) + filtered.get("to_move_to_ondemand", [])
        }
        # A node becomes drainable if all its current pods are being moved AND it isn't in kept_nodes
        node_pod_count: Dict[str, int] = {}
        for n in nodes:
            name_ = n.get("node_name")
            node_pod_count[name_] = int(
                (node_pod_counts or {}).get(name_, n.get("pod_count") or 0)
            )
        for n in nodes:
            name = n.get("node_name")
            if name in kept_nodes:
                continue
            # Anchor nodes are never drained regardless of pod count
            if name in anchor_nodes:
                continue
            count = node_pod_count.get(name, 0)
            # We can't tell pod-by-pod here without pod→node listing of OTHER workloads,
            # so only flag drain candidates when the node currently has only pods of the moving set.
            # Conservative: only mark drain when node has pod_count <= moves coming off it.
            pods_leaving_this_node = sum(
                1 for p in (filtered.get("to_move_to_spot", []) + filtered.get("to_move_to_ondemand", []))
                if p.get("node_name") == name
            )
            if count > 0 and pods_leaving_this_node >= count:
                node_plan.append({
                    "action": "drain",
                    "node_name": name,
                    "capacity_type": (n.get("capacity_type") or "on-demand").lower(),
                    "az": n.get("az"),
                    "instance_type": n.get("instance_type"),
                    "required_cpu_millicores": 0,
                    "required_memory_bytes": 0,
                    "pod_count": 0,
                    "reason": "consolidation_candidate",
                })

        return node_plan, warnings


# ---------------------------------------------------------------------------
# Submodule E — BinPacker
# ---------------------------------------------------------------------------

class BinPacker:
    """
    Assign each moved pod to a specific node (existing or to-be-provisioned).

    Algorithm: Best Fit Decreasing (BFD) with multi-factor scoring.
    Pods sorted by CPU descending; for each pod, all feasible nodes are scored
    and the best-scoring node is chosen.

    Scoring (lower = better):
        bfd_tightness   — normalised remaining CPU after placement (prefer tighter fit)
        hotspot_penalty — +HOTSPOT_PENALTY if utilisation after placement > 80%
        anchor_penalty  — +ANCHOR_PENALTY if non-critical pod would land on anchor node

    Four resource dimensions tracked in cursors:
        cpu_remaining, mem_remaining, pod_remaining, ip_remaining
    
    Enterprise Hardening (Part 2):
        ebs_slots_remaining - AWS EC2 EBS volume attachment limit
        network_bandwidth_available - simulated/measured bandwidth pressure
        conntrack_remaining - conntrack table utilization
        storage_remaining - nodefs/imagefs pressure
    """

    HOTSPOT_THRESHOLD = 0.80
    HOTSPOT_PENALTY = 150.0
    ANCHOR_PENALTY = 500.0
    CRITICAL_CONCENTRATION_PENALTY = 300.0
    
    # EBS attachment limit per instance (conservative default)
    # Some instances support up to 28, others more.
    DEFAULT_EBS_LIMIT = 25

    @staticmethod
    def pack(
        filtered: Dict[str, List[Dict[str, Any]]],
        node_plan: List[Dict[str, Any]],
        nodes: Optional[List[Dict[str, Any]]] = None,
        anchor_nodes: Optional[set] = None,
        anchor_map: Optional[Dict[str, str]] = None,
        node_pod_counts: Optional[Dict[str, int]] = None,
        node_ds_counts: Optional[Dict[str, int]] = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str], Dict[str, Any]]:
        """
        Returns (filtered_with_target_node, warnings, cursors).
        Each moved pod gets `target_node` set. Cursors are the final
        per-node resource state after all assignments — consumed by NodeLayoutBuilder.

        node_pod_counts / node_ds_counts: engine-derived counts from the pods
        list (preferred over node dict fields which may have pod_count=0 and
        no daemonset_count in the upstream data pipeline).
        """
        warnings: List[str] = []
        anchor_nodes = anchor_nodes or set()
        anchor_map = anchor_map or {}
        node_map: Dict[str, Dict] = {
            n.get("node_name"): n for n in (nodes or []) if n.get("node_name")
        }

        # Build per-node cursor using actual allocatable − used (not demand * 1.5)
        cursors: Dict[str, Dict[str, Any]] = {}
        for entry in node_plan:
            if entry["action"] == "drain":
                continue
            name = entry["node_name"]
            real = node_map.get(name, {})

            if entry["action"] == "keep":
                alloc_cpu = float(real.get("allocatable_cpu_millicores") or 4000)
                alloc_mem = float(real.get("allocatable_memory_bytes") or 16e9)
                max_pods  = int(real.get("max_pods") or K8S_MAX_PODS_PER_NODE)
                ds_pods   = int(
                    (node_ds_counts or {}).get(name, real.get("daemonset_count") or 0)
                )
                ip_avail  = int(real.get("ip_available") or 999)
                if entry.get("reason") == "drain_reuse":
                    # All non-DS pods are leaving this node; treat used resources as
                    # zero so BinPacker sees full capacity (matches CapacityPlanner check).
                    # DS pods stay and occupy pod slots only — their CPU/mem overhead is
                    # absorbed into the headroom since we have no per-DS resource sums.
                    used_cpu = 0.0
                    used_mem = 0.0
                    cur_pods = ds_pods
                else:
                    # Engine-derived counts take priority: node dict has pod_count=0
                    # and no daemonset_count field in the upstream data pipeline.
                    used_cpu = float(real.get("used_cpu_millicores") or 0)
                    used_mem = float(real.get("used_memory_bytes") or 0)
                    cur_pods = int(
                        (node_pod_counts or {}).get(name, real.get("pod_count") or 0)
                    )
            else:  # provision — new node, no current usage
                alloc_cpu = float(entry.get("allocatable_cpu_millicores") or 4000)
                alloc_mem = float(entry.get("allocatable_memory_bytes") or 16e9)
                used_cpu  = 0.0
                used_mem  = 0.0
                max_pods  = K8S_MAX_PODS_PER_NODE
                cur_pods  = 0
                ds_pods   = 0
                ip_avail  = 999

            cursors[name] = {
                "az": entry["az"],
                "capacity_type": entry["capacity_type"],
                "is_anchor": name in anchor_nodes,
                "allocatable_cpu": alloc_cpu,
                "allocatable_mem": alloc_mem,
                "cpu_remaining": alloc_cpu - used_cpu,
                "mem_remaining": alloc_mem - used_mem,
                "pod_remaining": max(0, max_pods - cur_pods - ds_pods),
                "ip_remaining": ip_avail,
                "ebs_slots_remaining": int(real.get("ebs_limit") or BinPacker.DEFAULT_EBS_LIMIT) - int(real.get("ebs_volume_count") or 0),
                "conntrack_utilization": float(real.get("conntrack_utilization") or 0.0),
                "storage_pressure": bool(real.get("storage_pressure")),
                "critical_pod_count": 0,
            }

        # BFD: sort pods by largest CPU first
        moves = (
            list(filtered.get("to_move_to_spot", []))
            + list(filtered.get("to_move_to_ondemand", []))
        )
        moves.sort(key=lambda p: float(p.get("cpu_request_millicores") or 0), reverse=True)

        for p in moves:
            pod_name   = p.get("pod_name", "")
            target_az  = p.get("target_az")
            target_cap = p.get("target_capacity_type")
            pcpu = float(p.get("cpu_request_millicores") or 0)
            pmem = float(p.get("memory_request_bytes") or 0)
            needs_ebs = bool(p.get("has_ebs_volume"))
            is_critical = pod_name in anchor_map
            preferred_anchor = anchor_map.get(pod_name)

            # Gather all feasible nodes (hard resource constraints)
            feasible = [
                name for name, cur in cursors.items()
                if (
                    cur["az"] == target_az
                    and cur["capacity_type"] == target_cap
                    and cur["cpu_remaining"] >= pcpu
                    and cur["mem_remaining"] >= pmem
                    and cur["pod_remaining"] > 0
                    and cur["ip_remaining"] > 0
                    # Hard Enterprise Constraints
                    and (not needs_ebs or cur["ebs_slots_remaining"] > 0)
                    and cur["conntrack_utilization"] < 0.85 # Conntrack safety margin
                    and not cur["storage_pressure"]         # Kubelet eviction safety
                )
            ]

            if not feasible:
                p["target_node"] = None
                p["blocked_by"] = "no_capacity"
                warnings.append(
                    f"no node fit for {pod_name} in {target_az}/{target_cap}"
                )
                continue

            # Critical pod with a preferred anchor node → assign directly if feasible
            if is_critical and preferred_anchor in feasible:
                chosen = preferred_anchor
            else:
                # BFD + multi-factor scoring (lower = better)
                def _score(name: str, _pcpu: float = pcpu) -> float:
                    cur = cursors[name]
                    alloc = max(cur["allocatable_cpu"], 1.0)
                    cpu_after = cur["cpu_remaining"] - _pcpu
                    # BFD tightness: prefer nodes with least remaining capacity after fit
                    s = cpu_after / alloc
                    # Hotspot penalty: avoid pushing node above 80% util
                    if (alloc - cpu_after) / alloc > BinPacker.HOTSPOT_THRESHOLD:
                        s += BinPacker.HOTSPOT_PENALTY
                    # Anchor penalty: avoid placing non-critical pods on anchor nodes
                    if cur["is_anchor"] and not is_critical:
                        s += BinPacker.ANCHOR_PENALTY
                    # Critical concentration penalty: discourage stacking 2+ critical pods
                    if is_critical and cur["critical_pod_count"] >= 1:
                        s += BinPacker.CRITICAL_CONCENTRATION_PENALTY
                    return s

                chosen = min(feasible, key=_score)

            cur = cursors[chosen]
            cur["cpu_remaining"] -= pcpu
            cur["mem_remaining"] -= pmem
            cur["pod_remaining"] -= 1
            cur["ip_remaining"]  -= 1
            if needs_ebs:
                cur["ebs_slots_remaining"] -= 1
            if is_critical:
                cur["critical_pod_count"] += 1
            p["target_node"] = chosen

        return filtered, warnings, cursors


# ---------------------------------------------------------------------------
# Post-Layer-3 Assembly — NodeLayoutBuilder
# ---------------------------------------------------------------------------

class NodeLayoutBuilder:
    """
    Runs immediately after BinPacker. Assembles the final node layout:
    - Groups ALL pods (existing + incoming) by target node
    - Computes before/after utilization per node
    - Classifies each node state: anchor | active | draining | provisioned
    - Groups keep-nodes by AZ for UI + Distribution Engine consumption

    Pure assembly — no new decisions. All data comes from cursors, filtered,
    node_plan, and the full pods list.
    """

    @staticmethod
    def build(
        filtered: Dict[str, List[Dict[str, Any]]],
        node_plan: List[Dict[str, Any]],
        cursors: Dict[str, Dict[str, Any]],
        anchor_nodes: set,
        all_pods: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Returns node_layout dict with by_az, drain_candidates, provision_required."""

        # Step 1: existing pods per node — DaemonSet pods included but labeled
        existing_by_node: Dict[str, List[Dict]] = {}
        ds_count_by_node: Dict[str, int] = {}
        for p in all_pods:
            node = p.get("node_name")
            if not node:
                continue
            ctrl_kind = (p.get("controller_kind") or "").lower()
            wclass    = (p.get("workload_class")   or "").lower()
            _is_ds = ctrl_kind == "daemonset" or wclass == "system" or is_system_pod(p)
            if _is_ds:
                ds_count_by_node[node] = ds_count_by_node.get(node, 0) + 1
            existing_by_node.setdefault(node, []).append({
                "pod_name":               p.get("pod_name"),
                "namespace":              p.get("namespace"),
                "workload_id":            p.get("workload_id"),
                "controller_kind":        p.get("controller_kind"),
                "capacity_type":          p.get("capacity_type"),
                "cpu_request_millicores": float(p.get("cpu_request_millicores") or 0),
                "memory_request_bytes":   float(p.get("memory_request_bytes") or 0),
                "status":                 p.get("status") or "Running",
                "is_daemonset":           _is_ds,
                "is_system":              is_system_pod(p),
            })

        # Step 2: incoming pods per target node
        incoming_by_node: Dict[str, List[Dict]] = {}
        all_moves = (
            filtered.get("to_move_to_spot", [])
            + filtered.get("to_move_to_ondemand", [])
        )
        for p in all_moves:
            target = p.get("target_node")
            if not target:
                continue
            incoming_by_node.setdefault(target, []).append({
                "pod_name":               p.get("pod_name"),
                "namespace":              p.get("namespace"),
                "workload_id":            p.get("workload_id"),
                "from_node":              p.get("node_name"),
                "from_az":                p.get("az"),
                "cpu_request_millicores": float(p.get("cpu_request_millicores") or 0),
                "memory_request_bytes":   float(p.get("memory_request_bytes") or 0),
                "movement_cost":          p.get("movement_cost"),
            })

        # Step 3: node action lookup + drain set
        node_action_map: Dict[str, Dict] = {
            e["node_name"]: e for e in node_plan if e.get("node_name")
        }
        drain_node_names: set = {
            e["node_name"] for e in node_plan
            if e.get("action") == "drain" and e.get("node_name")
        }

        # Step 4: assemble per-node entries
        by_az: Dict[str, Dict] = {}
        drain_candidates: List[Dict] = []
        provision_required: List[Dict] = []

        for node_name, cursor in cursors.items():
            az           = cursor["az"]
            cap          = cursor["capacity_type"]
            alloc_cpu    = cursor["allocatable_cpu"]
            alloc_mem    = cursor.get("allocatable_mem", 0.0)
            cpu_rem      = cursor["cpu_remaining"]
            mem_rem      = cursor["mem_remaining"]

            existing_pods = existing_by_node.get(node_name, [])
            incoming_pods = incoming_by_node.get(node_name, [])

            existing_cpu = sum(p["cpu_request_millicores"] for p in existing_pods)
            existing_mem = sum(p["memory_request_bytes"]   for p in existing_pods)
            incoming_cpu = sum(p["cpu_request_millicores"] for p in incoming_pods)
            incoming_mem = sum(p["memory_request_bytes"]   for p in incoming_pods)

            util_before = round(existing_cpu / alloc_cpu * 100 if alloc_cpu > 0 else 0.0, 1)
            util_after  = round(
                (alloc_cpu - cpu_rem) / alloc_cpu * 100 if alloc_cpu > 0 else 0.0, 1
            )

            action = node_action_map.get(node_name, {}).get("action", "keep")
            if node_name in anchor_nodes:
                state = "anchor"
            elif action == "drain":
                state = "draining"
            elif action == "provision":
                state = "provisioned"
            else:
                state = "active"

            _ds_count = ds_count_by_node.get(node_name, 0)
            _workload_pod_count = len(existing_pods) - _ds_count

            node_entry = {
                "node_name":           node_name,
                "capacity_type":       cap,
                "az":                  az,
                "state":               state,
                "is_anchor":           node_name in anchor_nodes,
                "action":              action,
                "existing_pods":       existing_pods,
                "existing_pod_count":  len(existing_pods),
                "daemonset_pod_count": _ds_count,
                "workload_pod_count":  _workload_pod_count,
                "incoming_pods":       incoming_pods,
                "incoming_pod_count":  len(incoming_pods),
                "resources": {
                    "allocatable_cpu_millicores": alloc_cpu,
                    "allocatable_memory_bytes":   alloc_mem,
                    "cpu_used_before_millicores":  existing_cpu,
                    "memory_used_before_bytes":    existing_mem,
                    "cpu_utilization_before_pct":  util_before,
                    "cpu_used_after_millicores":   existing_cpu + incoming_cpu,
                    "memory_used_after_bytes":     existing_mem + incoming_mem,
                    "cpu_utilization_after_pct":   util_after,
                    "cpu_remaining_millicores":    cpu_rem,
                    "memory_remaining_bytes":      mem_rem,
                    "pod_count_existing":          len(existing_pods),
                    "pod_count_incoming":          len(incoming_pods),
                    "pod_count_total_after":       len(existing_pods) + len(incoming_pods),
                    "daemonset_pod_count":         _ds_count,
                    "workload_pod_count":          _workload_pod_count,
                },
            }

            if state == "draining":
                drain_candidates.append(node_entry)
                continue

            if state == "provisioned":
                plan_entry = node_action_map.get(node_name, {})
                provision_required.append({
                    **node_entry,
                    "required_cpu_millicores": plan_entry.get("required_cpu_millicores"),
                    "required_memory_bytes":   plan_entry.get("required_memory_bytes"),
                    "instance_type":           plan_entry.get("instance_type"),
                })
                continue

            # anchor + active: group by AZ
            if az not in by_az:
                by_az[az] = {
                    "nodes": [],
                    "az_totals": {
                        "node_count": 0, "anchor_node_count": 0, "active_node_count": 0,
                        "pod_count_existing": 0, "pod_count_incoming": 0,
                        "pod_count_total_after": 0,
                        "cpu_used_before_millicores": 0.0,
                        "cpu_used_after_millicores": 0.0,
                        "cpu_remaining_millicores": 0.0,
                        "spot_node_count": 0, "ondemand_node_count": 0,
                    },
                }
            by_az[az]["nodes"].append(node_entry)
            t = by_az[az]["az_totals"]
            t["node_count"]                 += 1
            t["pod_count_existing"]         += len(existing_pods)
            t["pod_count_incoming"]         += len(incoming_pods)
            t["pod_count_total_after"]      += len(existing_pods) + len(incoming_pods)
            t["cpu_used_before_millicores"] += existing_cpu
            t["cpu_used_after_millicores"]  += existing_cpu + incoming_cpu
            t["cpu_remaining_millicores"]   += cpu_rem
            if state == "anchor":
                t["anchor_node_count"] += 1
            else:
                t["active_node_count"] += 1
            if cap == "spot":
                t["spot_node_count"] += 1
            else:
                t["ondemand_node_count"] += 1

        return {
            "by_az":              by_az,
            "drain_candidates":   drain_candidates,
            "provision_required": provision_required,
        }


# ---------------------------------------------------------------------------
# Layer 4 — CostProjector
# ---------------------------------------------------------------------------

class CostProjector:
    """
    Translate packing result into cost numbers.
    Run twice: pass 1 after BinPacker, pass 2 after PlanValidator finalises blocked_pods.

    Uses a simple heuristic (spot = 30% of OD) when a real pricing service is
    unavailable. Wire aws_pricing_service here when available.
    """

    MONTHLY_HOURS = 730
    SPOT_DISCOUNT_FACTOR = 0.65  # spot ~65% cheaper than OD (us-east-1 average)

    # Static OD on-demand hourly prices (us-east-1, Linux, 2025).
    # Wire aws_pricing_service into _hourly_rate() to replace with live prices.
    INSTANCE_HOURLY_OD_USD: Dict[str, float] = {
        # t3 family
        "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208,
        "t3.medium": 0.0416, "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
        # t3a family
        "t3a.nano": 0.0047, "t3a.micro": 0.0094, "t3a.small": 0.0188,
        "t3a.medium": 0.0376, "t3a.large": 0.0752, "t3a.xlarge": 0.1504, "t3a.2xlarge": 0.3008,
        # m5 family
        "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
        "m5.4xlarge": 0.768, "m5.8xlarge": 1.536, "m5.12xlarge": 2.304,
        "m5.16xlarge": 3.072, "m5.24xlarge": 4.608,
        # m6i family
        "m6i.large": 0.096, "m6i.xlarge": 0.192, "m6i.2xlarge": 0.384,
        "m6i.4xlarge": 0.768, "m6i.8xlarge": 1.536, "m6i.12xlarge": 2.304,
        # c5 family
        "c5.large": 0.085, "c5.xlarge": 0.17, "c5.2xlarge": 0.34,
        "c5.4xlarge": 0.68, "c5.9xlarge": 1.53, "c5.18xlarge": 3.06,
        # c6i family
        "c6i.large": 0.085, "c6i.xlarge": 0.17, "c6i.2xlarge": 0.34,
        "c6i.4xlarge": 0.68, "c6i.8xlarge": 1.36, "c6i.12xlarge": 2.04,
        # r5 family
        "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
        "r5.4xlarge": 1.008, "r5.8xlarge": 2.016, "r5.12xlarge": 3.024,
        # r6i family
        "r6i.large": 0.126, "r6i.xlarge": 0.252, "r6i.2xlarge": 0.504,
        "r6i.4xlarge": 1.008,
    }

    @staticmethod
    def _hourly_rate(instance_type: Optional[str], capacity_type: str) -> float:
        """
        Best-effort hourly rate using static instance price table.
        Falls back to $0.12/hr only for unknown instance types.
        Wire aws_pricing_service here to replace with live prices.
        """
        od_price = CostProjector.INSTANCE_HOURLY_OD_USD.get(
            (instance_type or "").lower().strip(), 0.12
        )
        if (capacity_type or "").lower() == "spot":
            return od_price * (1.0 - CostProjector.SPOT_DISCOUNT_FACTOR)
        return od_price

    @staticmethod
    def project(
        nodes: List[Dict[str, Any]],
        nodes_to_terminate: List[str],
        new_nodes_required: int = 0,
        blocked_pods: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Returns cost_projection dict:
        {
            current_nodes, projected_nodes,
            current_monthly_usd, projected_monthly_usd,
            saving_usd, saving_pct, spot_pct,
            actuals_updated
        }
        Pass blocked_pods on the second call so nodes needed only for blocked
        pods are excluded from the projected count.
        """
        terminate_set = set(nodes_to_terminate)

        current_cost = sum(
            CostProjector._hourly_rate(
                n.get("instance_type"), (n.get("capacity_type") or "on-demand").lower()
            )
            for n in nodes
        ) * CostProjector.MONTHLY_HOURS

        kept_nodes = [n for n in nodes if n.get("node_name") not in terminate_set]
        spot_kept = sum(
            1 for n in kept_nodes if (n.get("capacity_type") or "").lower() == "spot"
        )
        new_node_rate = CostProjector._hourly_rate(None, "on-demand")
        projected_cost = (
            sum(
                CostProjector._hourly_rate(
                    n.get("instance_type"), (n.get("capacity_type") or "on-demand").lower()
                )
                for n in kept_nodes
            ) + new_node_rate * new_nodes_required
        ) * CostProjector.MONTHLY_HOURS

        total_projected = len(kept_nodes) + new_nodes_required
        spot_pct = round(
            spot_kept / total_projected * 100 if total_projected > 0 else 0.0, 1
        )
        saving_usd = max(0.0, current_cost - projected_cost)
        saving_pct = round(saving_usd / current_cost * 100 if current_cost > 0 else 0.0, 1)

        return {
            "current_nodes": len(nodes),
            "projected_nodes": total_projected,
            "current_monthly_usd": round(current_cost, 2),
            "projected_monthly_usd": round(projected_cost, 2),
            "saving_usd": round(saving_usd, 2),
            "saving_pct": saving_pct,
            "spot_pct": spot_pct,
            "actuals_updated": False,
        }


# ---------------------------------------------------------------------------
# Layer 5 — PlanValidator
# ---------------------------------------------------------------------------

class PlanValidator:
    """
    Validate the full plan before any cluster operation runs.
    Catches infeasibility here — not at execution time.

    Hard checks (INFEASIBLE if violated and unabsorbable):
        MAX_PODS, IP_CAPACITY, STORAGE_AZ

    Soft checks (PARTIAL if violated):
        PDB, AZ_SPREAD
    """

    HARD_CHECKS = frozenset({"MAX_PODS", "IP_CAPACITY", "STORAGE_AZ"})
    SOFT_CHECKS = frozenset({"PDB", "AZ_SPREAD"})
    ALL_CHECKS = ["PDB", "IP_CAPACITY", "MAX_PODS", "STORAGE_AZ", "AZ_SPREAD"]

    @staticmethod
    def validate(
        movement_plan: List[Dict[str, Any]],
        nodes: List[Dict[str, Any]],
        wie: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns {
            "status":            "FEASIBLE" | "PARTIAL" | "INFEASIBLE",
            "validation_errors": [...],
            "blocked_pods":      [...],
            "passed_checks":     [...],
        }
        """
        validation_errors: List[Dict[str, Any]] = []
        blocked_pods: List[Dict[str, Any]] = []
        failed_checks: set = set()

        node_map: Dict[str, Dict] = {n.get("node_name", ""): n for n in nodes}
        pods_per_node: Dict[str, int] = {}
        for step in movement_plan:
            # Use to_virtual_node (provision target) when present; else real to_node.
            _dest = step.get("to_virtual_node") or step.get("to_node")
            if _dest:
                pods_per_node[_dest] = pods_per_node.get(_dest, 0) + 1

        # Check 1 — PDB safety (soft)
        # pdb_budget = max concurrent evictions allowed = running - pdb_min_available
        pdb_min = wie.get("pdb_min_available")
        running = wie.get("ready_replicas")
        if pdb_min is not None and running is not None:
            try:
                pdb_budget = max(0, int(running) - int(pdb_min))
                if pdb_budget == 0:
                    # Cannot safely evict even one pod
                    validation_errors.append({
                        "check": "PDB",
                        "workload": wie.get("workload_id", ""),
                        "reason": (
                            f"pdb_budget=0: min_available={pdb_min}, "
                            f"running={running} — no pods can move"
                        ),
                    })
                    failed_checks.add("PDB")
                    for step in movement_plan:
                        blocked_pods.append({
                            "pod": step.get("pod_name"),
                            "reason": "PDB_violation",
                        })
                elif len(movement_plan) > pdb_budget:
                    # Budget exceeded: block only the most-expensive excess pods
                    # (cheap pods move first — sort by movement_cost ASC, block tail)
                    excess = len(movement_plan) - pdb_budget
                    sorted_by_cost = sorted(
                        movement_plan,
                        key=lambda s: float(s.get("movement_cost") or 0),
                    )
                    for step in sorted_by_cost[-excess:]:
                        blocked_pods.append({
                            "pod": step.get("pod_name"),
                            "reason": "PDB_violation",
                        })
                    validation_errors.append({
                        "check": "PDB",
                        "workload": wie.get("workload_id", ""),
                        "reason": (
                            f"pdb_budget={pdb_budget}: blocked {excess} highest-cost pods, "
                            f"{pdb_budget} cheapest proceed"
                        ),
                    })
                    failed_checks.add("PDB")
            except (TypeError, ValueError):
                pass

        # Check 2 — IP capacity (hard)
        # Skip virtual/provision nodes: they don't exist yet, no real capacity to check.
        for node_name, assigned_count in pods_per_node.items():
            node = node_map.get(node_name)  # None for virtual provision nodes
            if not node:
                continue
            ip_avail = int(node.get("ip_available") or 0)
            if ip_avail > 0 and assigned_count > ip_avail:
                validation_errors.append({
                    "check": "IP_CAPACITY",
                    "node": node_name,
                    "reason": f"needs {assigned_count} IPs, available {ip_avail}",
                })
                failed_checks.add("IP_CAPACITY")

        # Check 3 — max_pods (hard)
        # Skip virtual/provision nodes: they don't exist yet, no real capacity to check.
        for node_name, incoming in pods_per_node.items():
            node = node_map.get(node_name)  # None for virtual provision nodes
            if not node:
                continue
            current_count = int(node.get("pod_count") or 0)
            limit = int(node.get("max_pods") or K8S_MAX_PODS_PER_NODE)
            total_after = current_count + incoming
            if total_after > limit:
                validation_errors.append({
                    "check": "MAX_PODS",
                    "node": node_name,
                    "reason": f"would have {total_after} pods, limit is {limit}",
                })
                failed_checks.add("MAX_PODS")

        # Check 4 — Storage AZ affinity (hard) — conservative: flag any STATEFUL cross-AZ move
        if (wie.get("data_safety") or "").upper() == "STATEFUL":
            for step in movement_plan:
                from_az = step.get("from_az") or step.get("current_az")
                to_az = step.get("to_az")
                if from_az and to_az and from_az != to_az:
                    validation_errors.append({
                        "check": "STORAGE_AZ",
                        "pod": step.get("pod_name"),
                        "reason": (
                            f"STATEFUL pod cross-AZ move: {from_az} → {to_az} "
                            "(RWO PV may be zone-locked)"
                        ),
                    })
                    failed_checks.add("STORAGE_AZ")
                    blocked_pods.append({
                        "pod": step.get("pod_name"),
                        "reason": "STORAGE_AZ_violation",
                    })

        # Check 5 — AZ spread feasibility (soft)
        az_spread_req = bool(
            wie.get("az_spread_required") or wie.get("has_topology_spread")
        )
        if az_spread_req and movement_plan:
            azs_in_plan = {
                step.get("to_az") for step in movement_plan if step.get("to_az")
            }
            if len(azs_in_plan) < 2:
                validation_errors.append({
                    "check": "AZ_SPREAD",
                    "reason": (
                        f"only {len(azs_in_plan)} AZ(s) in movement plan, ≥2 required"
                    ),
                })
                failed_checks.add("AZ_SPREAD")

        # Determine status
        hard_fails = failed_checks & PlanValidator.HARD_CHECKS
        soft_fails = failed_checks & PlanValidator.SOFT_CHECKS
        if hard_fails:
            status = "INFEASIBLE"
        elif soft_fails or blocked_pods:
            status = "PARTIAL"
        else:
            status = "FEASIBLE"

        passed_checks = [c for c in PlanValidator.ALL_CHECKS if c not in failed_checks]
        return {
            "status": status,
            "validation_errors": validation_errors,
            "blocked_pods": blocked_pods,
            "passed_checks": passed_checks,
        }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class PodPlacementEngine:
    """
    Main engine. Orchestrates 5 layers and returns a PlacementPlan.
    Pure function — no Redis/DB writes.
    """

    @staticmethod
    def materialize_plan(
        pods: List[Dict[str, Any]],
        nodes: List[Dict[str, Any]],
        wie: Dict[str, Any],
        targets: Dict[str, Any],
        in_flight_evictions: int = 0,
        cordoned_nodes: Optional[set] = None,
        cooldown_pods: Optional[set] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        anchor_settings: Optional[Dict[str, Any]] = None,
        data_age_seconds: Optional[float] = None,
        cluster_state: str = "idle",
        desired_hash: Optional[str] = None,
        cluster_id: Optional[str] = None,
    ) -> PlacementPlan:
        # ── Layer 1: StateGuard ────────────────────────────────────────────
        sg = StateGuard.check(
            pods, nodes,
            data_age_seconds=data_age_seconds,
            desired_hash=desired_hash,
            cluster_state=cluster_state,
        )
        if sg["decision"] == StateGuard.ABORT:
            logger.warning("PodPlacementEngine: StateGuard ABORT — %s", sg["reason"])
            return PodPlacementEngine._noop_plan(
                "stale_data" if "stale" in sg["reason"] else "cluster_not_idle",
                warnings=[sg["reason"]],
            )
        if sg["decision"] == StateGuard.NO_OP:
            logger.info("PodPlacementEngine: StateGuard NO_OP — %s", sg["reason"])
            return PodPlacementEngine._noop_plan("already_optimal", warnings=[sg["reason"]])

        # Guard: empty inputs → plan would be meaningless
        if not pods:
            logger.warning("PodPlacementEngine: no pods supplied — returning no-op plan")
            return PodPlacementEngine._noop_plan("no_pods_observed")
        if not nodes:
            logger.warning("PodPlacementEngine: no node data supplied — returning no-op plan")
            return PodPlacementEngine._noop_plan("no_node_data")

        # ── Diagnostic log: confirm targets the orchestrator wired into PPE ──────
        logger.info(
            "PPE.materialize_plan: targets received — od=%d spot=%d wie_max_spot=%d confidence=%s",
            int(targets.get("ondemand_target") or 0),
            int(targets.get("spot_target") or 0),
            int(wie.get("max_spot_replicas") or 0),
            wie.get("confidence_state", "UNKNOWN"),
        )
        if int(targets.get("spot_target") or 0) == 0 and int(wie.get("max_spot_replicas") or 0) > 0:
            logger.warning(
                "PPE.materialize_plan: targets.spot_target=0 but WIE says max_spot=%d — "
                "orchestrator may not be wiring WIE distribution to PPE targets",
                int(wie.get("max_spot_replicas") or 0),
            )

        feasibility_warnings: List[str] = []

        # ── Layer 2: AnchorPlanner ────────────────────────────────────────
        _anchor_settings = anchor_settings or {}
        anchor_result = AnchorPlanner.select(nodes, pods, wie, _anchor_settings)
        anchor_nodes: set = anchor_result["anchor_nodes"]
        locked_pods: set = anchor_result["locked_pods"]
        anchor_map: Dict[str, str] = anchor_result["anchor_map"]
        feasibility_warnings.extend(anchor_result["warnings"])

        # PodSelector — classify + score (skips locked/system pods)
        selected = PodSelector.classify_and_score(pods, wie, targets, locked_pods=locked_pods)

        # Guard: already optimal — nothing to move, skip remaining phases
        if not selected.get("to_move_to_spot") and not selected.get("to_move_to_ondemand"):
            logger.info("PodPlacementEngine: placement already optimal — no movements required")
            stay = selected.get("stay_put", [])
            all_stay = stay + selected.get("system_skip", [])
            spot_pods = [
                PodPlacementEngine._assignment_dict(p, target_cap="spot", moved=False)
                for p in stay if (p.get("capacity_type") or "").lower() == "spot"
            ]
            od_pods = [
                PodPlacementEngine._assignment_dict(p, target_cap="on-demand", moved=False)
                for p in stay if (p.get("capacity_type") or "").lower() != "spot"
            ]

            # Build current-state node layout so the Layout tab renders even with no moves
            _node_meta: Dict[str, Dict] = {n["node_name"]: n for n in nodes if n.get("node_name")}
            _pods_by_node: Dict[str, List] = {}
            for _p in all_stay:
                _nn = _p.get("node_name")
                if _nn:
                    _pods_by_node.setdefault(_nn, []).append(_p)

            _opt_node_plan: List[Dict] = []
            _opt_az_dist: Dict[str, Dict] = {}
            _opt_by_az: Dict[str, Dict] = {}

            for _nn, _node_pods in _pods_by_node.items():
                _nm = _node_meta.get(_nn, {})
                _az = _nm.get("az") or _nn.split(".")[0]
                _cap = _nm.get("capacity_type") or "on-demand"
                _alloc_cpu = float(_nm.get("allocatable_cpu_millicores") or 1)
                _used_cpu  = sum(float(_pp.get("cpu_request_millicores") or 0) for _pp in _node_pods)

                _opt_node_plan.append({
                    "action":                 "keep",
                    "node_name":              _nn,
                    "capacity_type":          _cap,
                    "az":                     _az,
                    "instance_type":          _nm.get("instance_type") or "unknown",
                    "required_cpu_millicores": _used_cpu,
                    "required_memory_bytes":  sum(float(_pp.get("memory_request_bytes") or 0) for _pp in _node_pods),
                    "pod_count":              len(_node_pods),
                    "reason":                 "already_optimal",
                })

                _is_spot = _cap.lower() == "spot"
                _az_entry = _opt_az_dist.setdefault(_az, {"spot": 0, "ondemand": 0, "total": 0})
                if _is_spot:
                    _az_entry["spot"] += len(_node_pods)
                else:
                    _az_entry["ondemand"] += len(_node_pods)
                _az_entry["total"] += len(_node_pods)

                _util = round(_used_cpu / _alloc_cpu * 100 if _alloc_cpu > 0 else 0.0, 1)
                _az_node_entry = _opt_by_az.setdefault(_az, {"nodes": [], "az_totals": {"node_count": 0, "pod_count_before": 0, "pod_count_total_after": 0, "spot_count": 0, "ondemand_count": 0}})
                _az_node_entry["nodes"].append({
                    "node_name":         _nn,
                    "capacity_type":     _cap,
                    "az":                _az,
                    "state":             "active",
                    "is_anchor":         _nn in anchor_nodes,
                    "action":            "keep",
                    "existing_pods":     [{"pod_name": _pp.get("pod_name"), "namespace": _pp.get("namespace"), "capacity_type": _cap, "cpu_request_millicores": float(_pp.get("cpu_request_millicores") or 0), "memory_request_bytes": float(_pp.get("memory_request_bytes") or 0), "status": "Running"} for _pp in _node_pods],
                    "existing_pod_count": len(_node_pods),
                    "incoming_pods":     [],
                    "incoming_pod_count": 0,
                    "resources":         {"cpu_utilization_before_pct": _util, "cpu_utilization_after_pct": _util, "allocatable_cpu_millicores": _alloc_cpu},
                })
                _t = _az_node_entry["az_totals"]
                _t["node_count"] += 1
                _t["pod_count_before"] += len(_node_pods)
                _t["pod_count_total_after"] += len(_node_pods)
                if _is_spot:
                    _t["spot_count"] += len(_node_pods)
                else:
                    _t["ondemand_count"] += len(_node_pods)

            _opt_sel_spot_cnt = len(selected.get("to_move_to_spot", []))
            _opt_spot_decision = {
                "selected": False,
                "reason": PodPlacementEngine._derive_spot_decision_reason(
                    spot_migration_selected=False,
                    spot_target=int(targets.get("spot_target") or 0),
                    wie_max_spot=int(wie.get("max_spot_replicas") or 0),
                    sel_spot_cnt=_opt_sel_spot_cnt,
                    filt_spot_cnt=0,
                    confidence=wie.get("confidence_state", "UNKNOWN"),
                ),
                "wie_eligible_spot": int(wie.get("max_spot_replicas") or 0),
                "planner_spot_target": int(targets.get("spot_target") or 0),
                "confidence_gate": wie.get("confidence_state") or "UNKNOWN",
                "spot_moves_planned": 0,
            }
            return PlacementPlan(
                schema_version=SCHEMA_VERSION,
                pod_assignment={"spot": spot_pods, "ondemand": od_pods},
                movement_plan=[],
                node_plan=_opt_node_plan,
                node_layout={"by_az": _opt_by_az, "drain_candidates": [], "provision_required": []},
                az_distribution=_opt_az_dist,
                feasibility={
                    "feasible":        True,
                    "status":          "already_optimal",
                    "plan_id":         hashlib.sha256(f"{id(pods)}{id(nodes)}0".encode()).hexdigest()[:12],
                    "cluster_id":      cluster_id,
                    "warnings":        feasibility_warnings,
                    "moves_total":     0,
                    "moves_blocked":   0,
                    "validator_status": "FEASIBLE",
                    "passed_checks":   [],
                },
                anchor_plan={
                    "anchor_nodes": list(anchor_nodes),
                    "locked_pods": list(locked_pods),
                    "anchor_count": anchor_result["anchor_count"],
                    "anchor_map": anchor_map,
                },
                cost_projection=CostProjector.project(nodes, [], 0),
                spot_migration_decision=_opt_spot_decision,
            )

        # StabilityOptimizer
        filtered, b_warnings = StabilityOptimizer.filter(
            selected, wie, targets,
            in_flight_evictions=in_flight_evictions,
            cordoned_nodes=cordoned_nodes,
            cooldown_pods=cooldown_pods,
            anchor_nodes=anchor_nodes,
            batch_size=batch_size,
        )
        feasibility_warnings.extend(b_warnings)

        # AZDistributor
        filtered, az_distribution, c_warnings = AZDistributor.assign(filtered, nodes, wie, targets)
        feasibility_warnings.extend(c_warnings)

        # Derive per-node pod/daemonset counts from the pods list.
        # The upstream node dict has pod_count=0 and no daemonset_count field;
        # computing from pods makes both CapacityPlanner and BinPacker self-sufficient.
        # CRITICAL: _node_pod_counts must only count WORKLOAD pods (not DaemonSet pods).
        # DaemonSet pods never leave a node — counting them causes false drain candidates:
        # if a node has 5 DS pods + 2 workload pods and we move 2 workload pods, the node
        # still has 5 DS pods so it is NOT drainable. Including DS pods in the count
        # would make pods_leaving(2) < count(7), correctly blocking drain — but if we
        # accidentally excluded DS from _node_pod_counts and included in leaving check,
        # drain would be triggered incorrectly. Keep them separate.
        _node_pod_counts: Dict[str, int] = {}  # workload-only pod count per node
        _node_ds_counts: Dict[str, int] = {}   # DaemonSet pod count per node (overhead)
        for _p in pods:
            _pnode = _p.get("node_name")
            if not _pnode:
                continue
            _is_ds = (
                (_p.get("controller_kind") or "").lower() == "daemonset"
                or (_p.get("workload_class") or "").lower() == "system"
                or is_system_pod(_p)
            )
            if _is_ds:
                _node_ds_counts[_pnode] = _node_ds_counts.get(_pnode, 0) + 1
            else:
                _node_pod_counts[_pnode] = _node_pod_counts.get(_pnode, 0) + 1

        # CapacityPlanner
        # Bug 2 fix: detect consolidation mode — when spot_target==0, the engine
        # is consolidating OD nodes and must NOT provision new spot nodes.
        # Passing consolidation_mode=True suppresses spot `provision` plan entries.
        _is_consolidation_mode = int(targets.get("spot_target") or 0) == 0
        node_plan, d_warnings = CapacityPlanner.plan(
            filtered, nodes,
            anchor_nodes=anchor_nodes,
            node_pod_counts=_node_pod_counts,
            consolidation_mode=_is_consolidation_mode,
        )
        feasibility_warnings.extend(d_warnings)

        # Augment node_plan with "keep" entries for nodes that host stay_put pods
        # but aren't already represented. CapacityPlanner only tracks nodes that
        # receive MOVING pods; stay_put nodes are invisible to it, so BinPacker
        # cursors and NodeLayoutBuilder would miss them entirely.
        _plan_node_names: set = {e["node_name"] for e in node_plan if e.get("node_name")}
        _node_meta_idx: Dict[str, Dict] = {n["node_name"]: n for n in nodes if n.get("node_name")}
        _stay_groups: Dict[str, List[Dict]] = {}
        for _sp in filtered.get("stay_put", []):
            _sn = _sp.get("node_name")
            if _sn and _sn not in _plan_node_names:
                _stay_groups.setdefault(_sn, []).append(_sp)
        _wie_class = wie.get("workload_class") or "stateless"
        for _sn, _sps in _stay_groups.items():
            _nm = _node_meta_idx.get(_sn, {})
            _cap = (_nm.get("capacity_type") or "on-demand").lower()
            _ret_reason = "anchor_node" if _sn in anchor_nodes else "fits_pods"
            node_plan.append({
                "action":                    "keep",
                "node_name":                 _sn,
                "capacity_type":             "on-demand" if _cap in ("on-demand", "ondemand") else _cap,
                "az":                        _nm.get("az") or "unknown",
                "instance_type":             _nm.get("instance_type"),
                "required_cpu_millicores":   sum(float(_p.get("cpu_request_millicores") or 0) for _p in _sps),
                "required_memory_bytes":     sum(float(_p.get("memory_request_bytes")   or 0) for _p in _sps),
                "pod_count":                 len(_sps),
                "retention_reason":          _ret_reason,
                "retained_workload_classes": [_wie_class],
            })

        # ── Layer 3: BinPacker ────────────────────────────────────────────

        filtered, e_warnings, _cursors = BinPacker.pack(
            filtered, node_plan,
            nodes=nodes,
            anchor_nodes=anchor_nodes,
            anchor_map=anchor_map,
            node_pod_counts=_node_pod_counts,
            node_ds_counts=_node_ds_counts,
        )
        feasibility_warnings.extend(e_warnings)

        # ── Post-Layer-3: NodeLayoutBuilder ──────────────────────────────────
        node_layout = NodeLayoutBuilder.build(
            filtered=filtered,
            node_plan=node_plan,
            cursors=_cursors,
            anchor_nodes=anchor_nodes,
            all_pods=pods,
        )

        # Build pod_assignment
        spot_pods, ondemand_pods = [], []
        for p in filtered.get("to_move_to_spot", []):
            spot_pods.append(PodPlacementEngine._assignment_dict(p, target_cap="spot", moved=True))
        for p in filtered.get("to_move_to_ondemand", []):
            ondemand_pods.append(PodPlacementEngine._assignment_dict(p, target_cap="on-demand", moved=True))
        for p in filtered.get("stay_put", []):
            cap = (p.get("capacity_type") or "on-demand").lower()
            cap_norm = "spot" if cap == "spot" else "on-demand"
            entry = PodPlacementEngine._assignment_dict(p, target_cap=cap_norm, moved=False)
            if cap_norm == "spot":
                spot_pods.append(entry)
            else:
                ondemand_pods.append(entry)

        # Build movement_plan
        # Provision node identity set: any target_node matching these names is a
        # future virtual node, not an existing real Kubernetes node.
        _prov_node_ids: set = {
            e["node_name"] for e in node_plan if e.get("action") == "provision"
        }

        movement_plan: List[Dict[str, Any]] = []
        step = 1
        for p in filtered.get("to_move_to_spot", []):
            _tgt = p.get("target_node")
            _is_virtual = _tgt in _prov_node_ids
            movement_plan.append({
                "step": step,
                "pod_name": p.get("pod_name"),
                "namespace": p.get("namespace"),
                "workload_id": wie.get("workload_id"),
                "from_node": p.get("node_name"),
                "from_az": p.get("az"),
                "from_capacity_type": (p.get("capacity_type") or "on-demand"),
                "to_capacity_type": "spot",
                "to_az": p.get("target_az"),
                "to_node": None if _is_virtual else _tgt,          # real node or None
                "to_virtual_node": _tgt if _is_virtual else None,  # synthetic ID or None
                "reason": "spot_target_unmet",
                "movement_cost": p.get("movement_cost"),
                "cpu_request_millicores": p.get("cpu_request_millicores"),
                "memory_request_bytes": p.get("memory_request_bytes"),
                "blocked_by": p.get("blocked_by"),
            })
            step += 1
        for p in filtered.get("to_move_to_ondemand", []):
            _tgt = p.get("target_node")
            _is_virtual = _tgt in _prov_node_ids
            movement_plan.append({
                "step": step,
                "pod_name": p.get("pod_name"),
                "namespace": p.get("namespace"),
                "workload_id": wie.get("workload_id"),
                "from_node": p.get("node_name"),
                "from_az": p.get("az"),
                "from_capacity_type": (p.get("capacity_type") or "spot"),
                "to_capacity_type": "on-demand",
                "to_az": p.get("target_az"),
                "to_node": None if _is_virtual else _tgt,          # real node or None
                "to_virtual_node": _tgt if _is_virtual else None,  # synthetic ID or None
                "reason": "ondemand_target_unmet",
                "movement_cost": p.get("movement_cost"),
                "cpu_request_millicores": p.get("cpu_request_millicores"),
                "memory_request_bytes": p.get("memory_request_bytes"),
                "blocked_by": p.get("blocked_by"),
            })
            step += 1

        # Movement budget: hard cap independent of PDB/batch calculations
        if len(movement_plan) > MAX_MOVES_PER_CYCLE:
            excess = len(movement_plan) - MAX_MOVES_PER_CYCLE
            movement_plan = movement_plan[:MAX_MOVES_PER_CYCLE]
            feasibility_warnings.append(
                f"movement_budget: capped at {MAX_MOVES_PER_CYCLE} moves/cycle — {excess} deferred"
            )

        # ── Layer 4: CostProjector — pass 1 (before validation) ────────────────
        drain_nodes = [
            e["node_name"] for e in node_plan if e.get("action") == "drain" and e.get("node_name")
        ]
        new_nodes_required = sum(
            1 for e in node_plan if e.get("action") == "provision"
        )
        cost_pass1 = CostProjector.project(nodes, drain_nodes, new_nodes_required)

        # ── Layer 5: PlanValidator ─────────────────────────────────────
        validation_result = PlanValidator.validate(movement_plan, nodes, wie)
        feasibility_warnings.extend(
            [e.get("reason", "") for e in validation_result["validation_errors"]]
        )

        # Remove validator-blocked pods from movement_plan
        blocked_pod_names = {b["pod"] for b in validation_result["blocked_pods"] if b.get("pod")}
        if blocked_pod_names:
            movement_plan = [s for s in movement_plan if s.get("pod_name") not in blocked_pod_names]

        # ── Layer 4: CostProjector — pass 2 (after validation) ──────────────
        cost_projection = CostProjector.project(
            nodes, drain_nodes, new_nodes_required,
            blocked_pods=validation_result["blocked_pods"],
        )
        cost_projection["preliminary"] = cost_pass1  # include pass-1 for comparison

        # Feasibility: partial (some blocked) vs infeasible (all blocked)
        blocked_by_capacity = [p for p in movement_plan if p.get("blocked_by") == "no_capacity"]
        n_blocked = len(blocked_by_capacity)
        n_total = len(movement_plan)
        validator_status = validation_result["status"]
        if validator_status == "INFEASIBLE":
            feasible, status = False, "infeasible"
        elif validator_status == "PARTIAL" or n_blocked > 0:
            feasible, status = True, "partial"
            if n_blocked > 0:
                feasibility_warnings.append(
                    f"{n_blocked} of {n_total} pods blocked by no_capacity — partial plan"
                )
        else:
            feasible, status = True, "plan_generated"

        _plan_id = hashlib.sha256(
            f"{id(pods)}{id(nodes)}{n_total}".encode()
        ).hexdigest()[:12]
        feasibility = {
            "feasible": feasible,
            "status": status,
            "plan_id": _plan_id,
            "cluster_id": cluster_id,
            "warnings": feasibility_warnings,
            "moves_total": n_total,
            "moves_blocked": n_blocked,
            "validator_status": validator_status,
            "passed_checks": validation_result["passed_checks"],
        }

        _spot_moves_cnt = sum(1 for m in movement_plan if m.get("to_capacity_type") == "spot")
        _spot_prov_cnt  = sum(
            1 for e in node_plan
            if e.get("action") == "provision" and (e.get("capacity_type") or "").lower() == "spot"
        )
        _spot_selected  = _spot_moves_cnt > 0 or _spot_prov_cnt > 0
        _spot_decision  = {
            "selected": _spot_selected,
            "reason": PodPlacementEngine._derive_spot_decision_reason(
                spot_migration_selected=_spot_selected,
                spot_target=int(targets.get("spot_target") or 0),
                wie_max_spot=int(wie.get("max_spot_replicas") or 0),
                sel_spot_cnt=len(selected.get("to_move_to_spot", [])),
                filt_spot_cnt=len(filtered.get("to_move_to_spot", [])),
                confidence=wie.get("confidence_state", "UNKNOWN"),
            ),
            "wie_eligible_spot": int(wie.get("max_spot_replicas") or 0),
            "planner_spot_target": int(targets.get("spot_target") or 0),
            "confidence_gate": wie.get("confidence_state") or "UNKNOWN",
            "spot_moves_planned": _spot_moves_cnt,
        }

        return PlacementPlan(
            schema_version=SCHEMA_VERSION,
            pod_assignment={"spot": spot_pods, "ondemand": ondemand_pods},
            movement_plan=movement_plan,
            node_plan=node_plan,
            node_layout=node_layout,
            az_distribution=az_distribution,
            feasibility=feasibility,
            anchor_plan={
                "anchor_nodes": list(anchor_nodes),
                "locked_pods": list(locked_pods),
                "anchor_count": anchor_result["anchor_count"],
                "anchor_map": anchor_map,
            },
            cost_projection=cost_projection,
            validation_errors=validation_result["validation_errors"],
            spot_migration_decision=_spot_decision,
        )

    @staticmethod
    def _noop_plan(status: str, warnings: Optional[List[str]] = None) -> "PlacementPlan":
        """Return an empty, no-op plan with an explanatory status. Never triggers any action."""
        return PlacementPlan(
            schema_version=SCHEMA_VERSION,
            pod_assignment={"spot": [], "ondemand": []},
            movement_plan=[],
            node_plan=[],
            node_layout={},
            az_distribution={},
            feasibility={
                "feasible": True,
                "status": status,
                "plan_id": None,
                "warnings": warnings or [],
                "moves_total": 0,
                "moves_blocked": 0,
                "validator_status": "FEASIBLE",
                "passed_checks": [],
            },
            anchor_plan={},
            cost_projection={},
            validation_errors=[],
        )

    @staticmethod
    def _derive_spot_decision_reason(
        spot_migration_selected: bool,
        spot_target: int,
        wie_max_spot: int,
        sel_spot_cnt: int,
        filt_spot_cnt: int,
        confidence: str,
    ) -> str:
        """Return a machine-readable reason code explaining the PPE spot migration decision."""
        if spot_migration_selected:
            return "spot_migration_executed"
        if spot_target == 0 and wie_max_spot > 0:
            return "spot_target_not_set_by_orchestrator"
        confidence_upper = (confidence or "UNKNOWN").upper()
        if sel_spot_cnt == 0 and confidence_upper not in ("CONFIRMED",):
            return "confidence_provisional_conservative_od_preferred"
        if sel_spot_cnt > 0 and filt_spot_cnt == 0:
            return "disruption_safety_blocked_all_spot_pods"
        if spot_target > 0 and sel_spot_cnt == 0 and confidence_upper == "CONFIRMED":
            return "existing_od_capacity_absorbed_spot_pods"
        return "spot_migration_not_needed"

    @staticmethod
    def _assignment_dict(p: Dict[str, Any], target_cap: str, moved: bool) -> Dict[str, Any]:
        return {
            "pod_name": p.get("pod_name"),
            "namespace": p.get("namespace"),
            "current_node": p.get("node_name"),
            "current_az": p.get("az"),
            "current_capacity_type": p.get("capacity_type"),
            "target_node": p.get("target_node") if moved else p.get("node_name"),
            "target_az": p.get("target_az") if moved else p.get("az"),
            "target_capacity_type": target_cap,
            "movement_required": moved,
            "movement_cost": p.get("movement_cost"),
            "blocked_by": p.get("blocked_by"),
        }