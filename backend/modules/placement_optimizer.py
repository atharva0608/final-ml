"""
Placement Optimizer (BFD-TSC v2)
==================================
Best-Fit Decreasing with Topology Spread Constraints.

Key improvements over v1:
- Uses AWS ENI-based max-pods table (official EKS limits) not a hardcoded 17
- Auto-solves node counts — no pre-specified od/spot/buffer required
- Overflow packing: spot-eligible pods placed on OD if it eliminates a spot node
- Auto-selects OD instance type from workload requirements
- Karpenter consolidation-aware: empty nodes never created
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TARGET_UTILIZATION = 0.65
OD_UTILIZATION     = 0.80
MAX_AZ_RATIO       = 0.60
HOURS_PER_MONTH    = 730

# ── AWS ENI-based max-pods table ───────────────────────────────────────────────
# Formula: min(max_eni × (max_ipv4_per_eni − 1) + 2, 110)
AWS_MAX_PODS: Dict[str, int] = {
    "t2.nano": 4,   "t2.micro": 4,   "t2.small": 11,  "t2.medium": 17,
    "t2.large": 35, "t2.xlarge": 44, "t2.2xlarge": 44,
    "t3.nano": 4,    "t3.micro": 4,   "t3.small": 11,  "t3.medium": 17,
    "t3.large": 35,  "t3.xlarge": 58, "t3.2xlarge": 58,
    "t3a.nano": 4,   "t3a.micro": 4,  "t3a.small": 11, "t3a.medium": 17,
    "t3a.large": 35, "t3a.xlarge": 58,"t3a.2xlarge": 58,
    "m5.large": 29,    "m5.xlarge": 58,    "m5.2xlarge": 58,
    "m5.4xlarge": 234, "m5.8xlarge": 234,  "m5.12xlarge": 234,
    "m5.16xlarge": 737,"m5.24xlarge": 737,
    "m5a.large": 29, "m5a.xlarge": 58, "m5a.2xlarge": 58, "m5a.4xlarge": 234,
    "m6i.large": 29,   "m6i.xlarge": 58,   "m6i.2xlarge": 58,   "m6i.4xlarge": 234,
    "m6i.8xlarge": 234,"m6i.12xlarge": 234,"m6i.16xlarge": 737, "m6i.24xlarge": 737,
    "m6a.large": 29, "m6a.xlarge": 58, "m6a.2xlarge": 58, "m6a.4xlarge": 234,
    "m6g.large": 29, "m6g.xlarge": 58, "m6g.2xlarge": 58, "m6g.4xlarge": 234,
    "c5.large": 29,   "c5.xlarge": 58,   "c5.2xlarge": 58,  "c5.4xlarge": 234,
    "c5.9xlarge": 234,"c5.12xlarge": 234,"c5.18xlarge": 737,"c5.24xlarge": 737,
    "c5a.large": 29,  "c5a.xlarge": 58,  "c5a.2xlarge": 58, "c5a.4xlarge": 234,
    "c6i.large": 29,  "c6i.xlarge": 58,  "c6i.2xlarge": 58, "c6i.4xlarge": 234,
    "c6a.large": 29,  "c6a.xlarge": 58,  "c6a.2xlarge": 58,
    "r5.large": 29,   "r5.xlarge": 58,   "r5.2xlarge": 58,   "r5.4xlarge": 234,
    "r5a.large": 29,  "r5a.xlarge": 58,  "r5a.2xlarge": 58,
    "r6i.large": 29,  "r6i.xlarge": 58,  "r6i.2xlarge": 58,  "r6i.4xlarge": 234,
    "r6g.large": 29,  "r6g.xlarge": 58,  "r6g.2xlarge": 58,
}

def max_pods_for(instance_type: str) -> int:
    mp = AWS_MAX_PODS.get(instance_type)
    if mp:
        return mp
    suffix = instance_type.split(".")[-1] if "." in instance_type else ""
    fallback = {"nano": 4, "micro": 4, "small": 11, "medium": 17, "large": 29,
                "xlarge": 58, "2xlarge": 58, "4xlarge": 234, "8xlarge": 234,
                "12xlarge": 234, "16xlarge": 737, "24xlarge": 737}
    return fallback.get(suffix, 29)

_OD_CATALOGUE: List[Tuple[str, int, float, float]] = [
    ("t3.medium",    2,   4.0, 0.0416),
    ("t3.large",     2,   8.0, 0.0832),
    ("t3.xlarge",    4,  16.0, 0.1664),
    ("t3.2xlarge",   8,  32.0, 0.3328),
    ("m5.large",     2,   8.0, 0.0960),
    ("m5.xlarge",    4,  16.0, 0.1920),
    ("m5.2xlarge",   8,  32.0, 0.3840),
    ("m5.4xlarge",  16,  64.0, 0.7680),
    ("m6i.large",    2,   8.0, 0.1008),
    ("m6i.xlarge",   4,  16.0, 0.2016),
    ("c5.large",     2,   4.0, 0.0850),
    ("c5.xlarge",    4,   8.0, 0.1700),
    ("r5.large",     2,  16.0, 0.1260),
    ("r5.xlarge",    4,  32.0, 0.2520),
]

@dataclass
class PodSpec:
    pod_name: str
    namespace: str
    cpu_request_millicores: int
    memory_request_mb: float
    is_stateful_by_nature: bool
    controller_kind: str = "Deployment"
    is_daemonset: bool = False
    is_control_plane: bool = False

@dataclass
class PoolInfo:
    instance_type: str
    az: str
    family: str
    lifecycle: str
    hourly_cost: float
    interruption_probability: float
    vcpu: int
    memory_gb: float

    @property
    def cpu_capacity_millicores(self) -> int:
        return self.vcpu * 1000

    @property
    def memory_capacity_mb(self) -> float:
        return self.memory_gb * 1024

    @property
    def max_pods(self) -> int:
        return max_pods_for(self.instance_type)

@dataclass
class PlacementNode:
    pool: PoolInfo
    role: str
    assigned_pods: List[str] = field(default_factory=list)
    cpu_used_millicores: int = 0
    memory_used_mb: float = 0.0

    @property
    def _util_factor(self) -> float:
        return OD_UTILIZATION if self.pool.lifecycle == "on-demand" else TARGET_UTILIZATION

    @property
    def cpu_free_millicores(self) -> int:
        return int(self.pool.cpu_capacity_millicores * self._util_factor) - self.cpu_used_millicores

    @property
    def memory_free_mb(self) -> float:
        return self.pool.memory_capacity_mb * self._util_factor - self.memory_used_mb

    def can_fit(self, pod: PodSpec) -> bool:
        if len(self.assigned_pods) >= self.pool.max_pods:
            return False
        return (
            self.cpu_free_millicores >= pod.cpu_request_millicores
            and self.memory_free_mb  >= pod.memory_request_mb
        )

    def assign(self, pod: PodSpec) -> None:
        self.assigned_pods.append(pod.pod_name)
        self.cpu_used_millicores += pod.cpu_request_millicores
        self.memory_used_mb      += pod.memory_request_mb

@dataclass
class PlacementResult:
    od_nodes: List[PlacementNode]
    spot_nodes: List[PlacementNode]
    buffer_nodes: List[PlacementNode]
    stateful_pods: int
    spot_friendly_pods: int
    misplaced_pods: int
    placement_score: float
    current_monthly_cost: float
    recommended_monthly_cost: float
    savings_monthly: float
    savings_pct: float
    az_distribution: Dict[str, int]
    family_distribution: Dict[str, int]
    max_az_concentration_pct: float
    max_family_concentration_pct: float
    interruption_probability: float
    warnings: List[str]

    def to_dict(self) -> dict:
        all_nodes = self.od_nodes + self.spot_nodes + self.buffer_nodes
        return {
            "od_nodes":     len(self.od_nodes),
            "spot_nodes":   len(self.spot_nodes),
            "buffer_nodes": len(self.buffer_nodes),
            "total_nodes":  len(all_nodes),
            "monthly_cost": round(self.recommended_monthly_cost, 2),
            "savings_monthly": round(self.savings_monthly, 2),
            "savings_pct":  round(self.savings_pct, 1),
            "node_breakdown": [
                {
                    "type":      n.pool.instance_type,
                    "lifecycle": n.pool.lifecycle,
                    "role":      n.role,
                    "az":        n.pool.az,
                    "hourly":    round(n.pool.hourly_cost, 4),
                    "monthly":   round(n.pool.hourly_cost * HOURS_PER_MONTH, 2),
                    "vcpu":      n.pool.vcpu,
                    "memory_gb": n.pool.memory_gb,
                    "max_pods":  n.pool.max_pods,
                    "pods":      len(n.assigned_pods),
                    "pod_names": list(n.assigned_pods),
                    "cpu_capacity_millicores": n.pool.cpu_capacity_millicores,
                    "memory_capacity_mb": round(n.pool.memory_capacity_mb, 1),
                    "cpu_used_millicores":  n.cpu_used_millicores,
                    "memory_used_mb": round(n.memory_used_mb, 1),
                }
                for n in all_nodes
            ],
            "az_distribution":     self.az_distribution,
            "family_distribution": self.family_distribution,
            "risk_summary": {
                "interruption_probability": round(self.interruption_probability, 3),
                "interruption_label": _interruption_label(self.interruption_probability),
                "max_az_concentration_pct":    round(self.max_az_concentration_pct, 1),
                "max_family_concentration_pct": round(self.max_family_concentration_pct, 1),
            },
            "placement_score": round(self.placement_score, 3),
            "warnings":        self.warnings,
        }


class PlacementOptimizer:
    """Two-phase hybrid placement optimizer (v3).

    Phase 1 – Hard separation:
        - Stateful pods: on-demand nodes ONLY (never spot).
        - Spot-eligible pods: spot preferred; overflow to OD allowed.

    Phase 2 – Exhaustive search:
        Enumerate top-N (od_pool, spot_pool, O, S) combinations and return
        the cheapest configuration that places every pod.

    Instance constraints:
        - Minimum 2 vCPU / 4 GiB RAM (no nano/micro in either pool).
        - Minimum 3 spot nodes when any spot is used (one per AZ for diversity).
        - AWS ENI-based max-pods enforced per node.
    """

    # Minimum viable instance constraints (excludes nano/micro)
    MIN_VCPU     = 2
    MIN_MEM_GB   = 4.0
    MIN_MAX_PODS = 11
    # Minimum spot nodes to spread across AZs
    MIN_SPOT_NODES = 3

    def __init__(
        self,
        available_pools: Optional[List[PoolInfo]] = None,
        available_azs:   Optional[List[str]]      = None,
    ):
        self.available_pools = available_pools or []
        self.available_azs   = available_azs or ["ap-south-1a", "ap-south-1b"]

        # Pre-filter: exclude nano/micro instances
        self._viable_od_pools: List[PoolInfo] = [
            p for p in self.available_pools
            if p.lifecycle == "on-demand"
            and p.vcpu      >= self.MIN_VCPU
            and p.memory_gb >= self.MIN_MEM_GB
            and p.max_pods  >= self.MIN_MAX_PODS
        ]
        self._viable_spot_pools: List[PoolInfo] = [
            p for p in self.available_pools
            if p.lifecycle == "spot"
            and p.vcpu      >= self.MIN_VCPU
            and p.memory_gb >= self.MIN_MEM_GB
            and p.max_pods  >= self.MIN_MAX_PODS
        ]

    # ── Public API ─────────────────────────────────────────────────────────────

    def compute_optimal_placement(
        self,
        pods:                 List[PodSpec],
        od_node_count:        Optional[int] = None,
        spot_node_count:      Optional[int] = None,
        buffer_node_count:    Optional[int] = None,
        current_monthly_cost: float         = 0.0,
    ) -> "PlacementResult":
        # ── Skip DaemonSets: they run on every node automatically ──────────
        # DaemonSets should not be placed by the optimizer; Kubernetes
        # schedules them on every node via the DaemonSet controller.
        placeable_pods = [p for p in pods if not p.is_daemonset]
        skipped_daemonsets = len(pods) - len(placeable_pods)
        if skipped_daemonsets:
            logger.info(f"Skipping {skipped_daemonsets} DaemonSet pod(s) from placement")

        # ── Separate control-plane pods for round-robin spreading ──────────
        control_plane_pods = sorted(
            [p for p in placeable_pods if p.is_control_plane],
            key=lambda p: p.cpu_request_millicores + p.memory_request_mb * 0.5,
            reverse=True,
        )

        stateful_pods = sorted(
            [p for p in placeable_pods if p.is_stateful_by_nature and not p.is_control_plane],
            key=lambda p: p.cpu_request_millicores + p.memory_request_mb * 0.5,
            reverse=True,
        )
        spot_pods = sorted(
            [p for p in placeable_pods if not p.is_stateful_by_nature],
            key=lambda p: p.cpu_request_millicores + p.memory_request_mb * 0.5,
            reverse=True,
        )
        buf = buffer_node_count or 0

        if od_node_count is not None and spot_node_count is not None:
            return self._placement_with_counts(
                stateful_pods, spot_pods, od_node_count, spot_node_count, buf,
                current_monthly_cost, control_plane_pods=control_plane_pods,
            )
        return self._search_optimal_placement(
            stateful_pods, spot_pods, buf, current_monthly_cost,
            control_plane_pods=control_plane_pods,
        )

    def compute_adjustable_params(
        self,
        pods:           List[PodSpec],
        current_od:     int,
        current_spot:   int,
        current_buffer: int,
    ) -> dict:
        placeable = [p for p in pods if not p.is_daemonset]
        stateful  = [p for p in placeable if p.is_stateful_by_nature]
        spot_elig = [p for p in placeable if not p.is_stateful_by_nature]
        od_pool   = (self._get_od_candidates(stateful)    or
                     [_make_od_pool("m5.large", 2, 8.0, 0.0960, self.available_azs[0])])[0]
        spot_pool = (self._get_spot_candidates(spot_elig) or
                     [_make_od_pool("m5.large", 2, 8.0, 0.0300, self.available_azs[0], lifecycle="spot")])[0]

        od_rec   = max(1, self._min_nodes_for(stateful, od_pool))
        raw_spot = self._min_nodes_for(spot_elig, spot_pool)
        spot_rec = max(self.MIN_SPOT_NODES, raw_spot) if raw_spot > 0 else 0

        return {
            "od_node_count":     {"min": max(1, od_rec - 1), "max": od_rec + 3,    "recommended": od_rec,   "current": current_od},
            "spot_node_count":   {"min": 0,                   "max": spot_rec + 4,  "recommended": spot_rec, "current": current_spot},
            "buffer_node_count": {"min": 0,                   "max": 3,             "recommended": 1 if spot_rec > 0 else 0, "current": current_buffer},
            "target_spot_pct": {
                "min": 0, "max": 80,
                "recommended": round(len(spot_elig) / len(pods) * 100) if pods else 0,
                "current":     round(current_spot / (current_od + current_spot) * 100)
                               if (current_od + current_spot) > 0 else 0,
            },
        }

    # ── Exhaustive search ──────────────────────────────────────────────────────

    def _search_optimal_placement(
        self,
        stateful_pods:        List[PodSpec],
        spot_pods:            List[PodSpec],
        buffer_count:         int,
        current_monthly_cost: float,
        control_plane_pods:   Optional[List[PodSpec]] = None,
    ) -> "PlacementResult":
        """Enumerate top-4 (od_pool, spot_pool, O, S) combos; return cheapest valid."""
        _cp_pods = control_plane_pods or []
        # Control-plane pods also need OD capacity
        _all_od_pods = stateful_pods + _cp_pods
        od_candidates   = self._get_od_candidates(_all_od_pods)[:4]
        spot_candidates = self._get_spot_candidates(spot_pods)[:4]
        valid_results: List["PlacementResult"] = []

        for od_pool in od_candidates:
            min_od = max(1, self._min_nodes_for(_all_od_pods, od_pool))
            # Ensure at least 2 OD nodes when control-plane pods exist (HA)
            if _cp_pods and min_od < 2:
                min_od = 2

            for spot_pool in spot_candidates:
                raw_min_spot = self._min_nodes_for(spot_pods, spot_pool)
                # Enforce ≥ 3 spot nodes for AZ diversity when spot is needed.
                min_spot = max(self.MIN_SPOT_NODES, raw_min_spot) if raw_min_spot > 0 else 0

                for O in range(min_od, min_od + 3):
                    s_range = [0] if min_spot == 0 else range(min_spot, min_spot + 4)
                    for S in s_range:
                        result = self._try_placement(
                            stateful_pods, spot_pods, od_pool, spot_pool,
                            O, S, buffer_count, current_monthly_cost,
                            control_plane_pods=_cp_pods,
                        )
                        if result is not None and result.misplaced_pods == 0:
                            valid_results.append(result)

        if not valid_results:
            return self._fallback_placement(
                stateful_pods, spot_pods, buffer_count, current_monthly_cost,
                control_plane_pods=_cp_pods,
            )

        valid_results.sort(
            key=lambda r: (round(r.recommended_monthly_cost, 2), -r.placement_score)
        )
        return valid_results[0]

    def _try_placement(
        self,
        stateful_pods:        List[PodSpec],
        spot_pods:            List[PodSpec],
        od_pool_tmpl:         PoolInfo,
        spot_pool_tmpl:       PoolInfo,
        od_count:             int,
        spot_count:           int,
        buffer_count:         int,
        current_monthly_cost: float,
        control_plane_pods:   Optional[List[PodSpec]] = None,
    ) -> Optional["PlacementResult"]:
        """
        Attempt placement with the given pool templates and node counts.
        Returns None only if stateful pods cannot all fit (hard constraint).
        Returns PlacementResult with misplaced_pods > 0 if overflow is incomplete.
        """
        warnings: List[str] = []
        _cp_pods = control_plane_pods or []

        # Phase 1: First-Fit Decreasing → OD nodes (hard OD-only for stateful)
        od_nodes, unfit_stateful = self._pack_ffd(
            stateful_pods, od_pool_tmpl, od_count, "od_stateful"
        )
        if unfit_stateful:
            return None  # hard constraint: stateful must fit — skip this config

        # Phase 1b: Spread control-plane pods round-robin across OD nodes
        # This prevents packing coredns, karpenter, metrics-server onto one node.
        if _cp_pods:
            # Ensure we have enough OD nodes to spread across
            while len(od_nodes) < min(od_count, 2) and len(od_nodes) < od_count:
                od_nodes.append(PlacementNode(
                    pool=_pool_for_az(od_pool_tmpl, self.available_azs, len(od_nodes)),
                    role="od_stateful",
                ))
            unfit_cp: List[PodSpec] = []
            for idx, pod in enumerate(_cp_pods):
                placed = False
                # Round-robin: try starting from node (idx % len) for even distribution
                n_count = len(od_nodes)
                for offset in range(n_count):
                    node = od_nodes[(idx + offset) % n_count]
                    if node.can_fit(pod):
                        node.assign(pod)
                        placed = True
                        break
                if not placed:
                    unfit_cp.append(pod)
            if unfit_cp:
                warnings.append(
                    f"{len(unfit_cp)} control-plane pod(s) could not fit on OD nodes."
                )

        # Phase 2: BFD-TSC → spot nodes (spot-eligible pods)
        spot_nodes, unfit_spot = self._pack_bfd_tsc(spot_pods, spot_pool_tmpl, spot_count)

        # Phase 3: Overflow — unfit spot pods try existing OD nodes (allowed)
        overflow_fit:   List[str]     = []
        overflow_unfit: List[PodSpec] = []
        for pod in sorted(
            unfit_spot,
            key=lambda p: p.cpu_request_millicores + p.memory_request_mb * 0.5,
            reverse=True,
        ):
            placed = False
            for node in sorted(od_nodes, key=lambda n: n.cpu_free_millicores, reverse=True):
                if node.can_fit(pod):
                    node.assign(pod)
                    overflow_fit.append(pod.pod_name)
                    placed = True
                    break
            if not placed:
                overflow_unfit.append(pod)

        if overflow_fit:
            warnings.append(
                f"Overflow: {len(overflow_fit)} spot-eligible pod(s) placed on OD "
                f"(spot pool at capacity)."
            )
        if overflow_unfit:
            warnings.append(
                f"{len(overflow_unfit)} pod(s) could not fit in "
                f"{od_count} OD + {spot_count} spot nodes."
            )

        # Phase 4: Buffer nodes
        buffer_nodes: List[PlacementNode] = [
            PlacementNode(
                pool=_pool_for_az(spot_pool_tmpl, self.available_azs, len(spot_nodes) + i),
                role="buffer",
            )
            for i in range(buffer_count)
        ]

        # Phase 5: High-utilisation warnings
        for n in spot_nodes:
            if n.assigned_pods:
                util = n.cpu_used_millicores / max(n.pool.cpu_capacity_millicores, 1)
                if util > 0.85:
                    warnings.append(
                        f"Spot node ({n.pool.instance_type}) at {util*100:.0f}% CPU "
                        f"— consider adding a buffer node."
                    )

        all_nodes = od_nodes + spot_nodes + buffer_nodes
        score, metrics = self._score_placement(all_nodes, spot_nodes)
        rec_cost    = sum(n.pool.hourly_cost * HOURS_PER_MONTH for n in all_nodes)
        savings     = max(0.0, current_monthly_cost - rec_cost)
        savings_pct = (savings / current_monthly_cost * 100) if current_monthly_cost > 0 else 0.0

        return PlacementResult(
            od_nodes=od_nodes, spot_nodes=spot_nodes, buffer_nodes=buffer_nodes,
            stateful_pods=len(stateful_pods), spot_friendly_pods=len(spot_pods),
            misplaced_pods=len(overflow_unfit),
            placement_score=score,
            current_monthly_cost=current_monthly_cost,
            recommended_monthly_cost=rec_cost,
            savings_monthly=savings, savings_pct=savings_pct,
            az_distribution=metrics["az_distribution"],
            family_distribution=metrics["family_distribution"],
            max_az_concentration_pct=metrics["max_az_concentration_pct"],
            max_family_concentration_pct=metrics["max_family_concentration_pct"],
            interruption_probability=metrics["interruption_probability"],
            warnings=warnings,
        )

    def _placement_with_counts(
        self,
        stateful_pods:        List[PodSpec],
        spot_pods:            List[PodSpec],
        od_count:             int,
        spot_count:           int,
        buffer_count:         int,
        current_monthly_cost: float,
        control_plane_pods:   Optional[List[PodSpec]] = None,
    ) -> "PlacementResult":
        _cp_pods = control_plane_pods or []
        _all_od_pods = stateful_pods + _cp_pods
        od_pool   = (self._get_od_candidates(_all_od_pods) or
                     [_make_od_pool("m5.large", 2, 8.0, 0.0960, self.available_azs[0])])[0]
        spot_pool = (self._get_spot_candidates(spot_pods)   or
                     [_make_od_pool("m5.large", 2, 8.0, 0.0300, self.available_azs[0], lifecycle="spot")])[0]
        result = self._try_placement(
            stateful_pods, spot_pods, od_pool, spot_pool,
            od_count, spot_count, buffer_count, current_monthly_cost,
            control_plane_pods=_cp_pods,
        )
        if result is not None:
            return result
        return self._fallback_placement(
            stateful_pods, spot_pods, buffer_count, current_monthly_cost,
            control_plane_pods=_cp_pods,
        )

    # ── Bin-packing helpers ────────────────────────────────────────────────────

    def _pack_ffd(
        self,
        pods:      List[PodSpec],
        pool_tmpl: PoolInfo,
        max_nodes: int,
        role:      str,
    ) -> Tuple[List[PlacementNode], List[PodSpec]]:
        """First-Fit Decreasing. Returns (placed_nodes, unfit_pods)."""
        nodes: List[PlacementNode] = []
        unfit: List[PodSpec]       = []
        for pod in pods:
            placed = False
            for node in nodes:
                if node.can_fit(pod):
                    node.assign(pod)
                    placed = True
                    break
            if not placed:
                if len(nodes) < max_nodes:
                    nn = PlacementNode(
                        pool=_pool_for_az(pool_tmpl, self.available_azs, len(nodes)),
                        role=role,
                    )
                    nn.assign(pod)
                    nodes.append(nn)
                else:
                    unfit.append(pod)
        return nodes, unfit

    def _pack_bfd_tsc(
        self,
        pods:      List[PodSpec],
        pool_tmpl: PoolInfo,
        max_nodes: int,
    ) -> Tuple[List[PlacementNode], List[PodSpec]]:
        """Best-Fit Decreasing with Topology Spread Constraints.

        Diversity priority order for each pod:
          1. Capacity fits + AZ diversity met  -> BFD (tightest-fit first)
          2. Capacity fits + AZ diversity relaxed -> still place (no scale-out)
          3. No node can fit -> scale out (new node, up to max_nodes)
          4. max_nodes reached -> pod goes to unfit

        Capacity constraints are NEVER relaxed.
        """
        nodes: List[PlacementNode] = []
        unfit: List[PodSpec]       = []
        for pod in pods:
            fitting = [n for n in nodes if n.can_fit(pod)]

            # Step 1: diversity-OK, BFD order (smallest free = tightest fit)
            diversity_ok = sorted(
                [n for n in fitting if self._az_diversity_ok(n, nodes)],
                key=lambda n: n.cpu_free_millicores,
            )
            if diversity_ok:
                diversity_ok[0].assign(pod)
                continue

            # Step 2: relax AZ constraint — capacity still enforced
            if fitting:
                fitting.sort(key=lambda n: n.cpu_free_millicores)
                fitting[0].assign(pod)
                continue

            # Step 3: scale out
            if len(nodes) < max_nodes:
                nn = PlacementNode(
                    pool=_pool_for_az(pool_tmpl, self.available_azs, len(nodes)),
                    role="spot_stateless",
                )
                nn.assign(pod)
                nodes.append(nn)
            else:
                unfit.append(pod)

        return nodes, unfit

    def _min_nodes_for(self, pods: List[PodSpec], pool_tmpl: PoolInfo) -> int:
        """Minimum nodes of pool_tmpl type needed to fit all pods (BFD simulation)."""
        if not pods:
            return 0
        nodes: List[PlacementNode] = []
        for pod in pods:
            placed = False
            for node in sorted(nodes, key=lambda n: n.cpu_free_millicores, reverse=True):
                if node.can_fit(pod):
                    node.assign(pod)
                    placed = True
                    break
            if not placed:
                nn = PlacementNode(
                    pool=_pool_for_az(pool_tmpl, self.available_azs, len(nodes)),
                    role="_sim",
                )
                nn.assign(pod)
                nodes.append(nn)
        return len(nodes)

    # ── Pool selection ─────────────────────────────────────────────────────────

    def _get_od_candidates(self, pods: Optional[List[PodSpec]] = None) -> List[PoolInfo]:
        """Viable OD pools sorted by hourly cost asc. Falls back to _OD_CATALOGUE."""
        # Deduplicate by instance_type, keep cheapest per type
        seen: Dict[str, PoolInfo] = {}
        for p in sorted(self._viable_od_pools, key=lambda p: p.hourly_cost):
            if p.instance_type not in seen:
                seen[p.instance_type] = p
        candidates = list(seen.values())

        if candidates and pods:
            avg_cpu = sum(p.cpu_request_millicores for p in pods) / len(pods)
            avg_mem = sum(p.memory_request_mb      for p in pods) / len(pods)
            good = [
                c for c in candidates
                if c.cpu_capacity_millicores * OD_UTILIZATION >= avg_cpu * 2
                and c.memory_capacity_mb     * OD_UTILIZATION >= avg_mem * 2
            ]
            if good:
                return sorted(good, key=lambda p: p.hourly_cost)

        if candidates:
            return sorted(candidates, key=lambda p: p.hourly_cost)

        # No OD in ML rankings — build from hardcoded catalogue
        az = self.available_azs[0] if self.available_azs else "ap-south-1a"
        fallback = [
            _make_od_pool(itype, vcpu, mem_gb, hourly, az)
            for itype, vcpu, mem_gb, hourly in _OD_CATALOGUE
            if vcpu >= self.MIN_VCPU
            and mem_gb >= self.MIN_MEM_GB
            and max_pods_for(itype) >= self.MIN_MAX_PODS
        ]
        return sorted(fallback, key=lambda p: p.hourly_cost)

    def _get_spot_candidates(self, pods: Optional[List[PodSpec]] = None) -> List[PoolInfo]:
        """Viable spot pools sorted by risk+cost. Falls back if none available."""
        if not self._viable_spot_pools:
            az = self.available_azs[0] if self.available_azs else "ap-south-1a"
            return [_make_od_pool("m5.large", 2, 8.0, 0.0300, az, lifecycle="spot")]

        # Score = interruption_prob * 0.6 + hourly_cost * 0.4
        scored = sorted(
            self._viable_spot_pools,
            key=lambda p: p.interruption_probability * 0.6 + p.hourly_cost * 0.4,
        )
        seen: Dict[str, PoolInfo] = {}
        for p in scored:
            if p.instance_type not in seen:
                seen[p.instance_type] = p
        candidates = sorted(
            seen.values(),
            key=lambda p: p.interruption_probability * 0.6 + p.hourly_cost * 0.4,
        )

        if pods:
            avg_cpu = sum(p.cpu_request_millicores for p in pods) / len(pods)
            avg_mem = sum(p.memory_request_mb      for p in pods) / len(pods)
            # Must fit at least 2 average pods comfortably
            good = [
                c for c in candidates
                if c.cpu_capacity_millicores * TARGET_UTILIZATION >= avg_cpu * 2
                and c.memory_capacity_mb     * TARGET_UTILIZATION >= avg_mem * 2
            ]
            if good:
                return good

        return candidates

    def _fallback_placement(
        self,
        stateful_pods:        List[PodSpec],
        spot_pods:            List[PodSpec],
        buffer_count:         int,
        current_monthly_cost: float,
        control_plane_pods:   Optional[List[PodSpec]] = None,
    ) -> "PlacementResult":
        """Last-resort: largest available instance, auto-grow until all pods fit."""
        warnings = ["Fallback mode: unconstrained placement to guarantee all pods fit."]
        _cp_pods = control_plane_pods or []

        od_pool = (
            sorted(self._viable_od_pools, key=lambda p: p.vcpu, reverse=True) or
            [_make_od_pool("m5.large", 2, 8.0, 0.0960, self.available_azs[0])]
        )[0]
        spot_pool = (
            sorted(self._viable_spot_pools, key=lambda p: p.vcpu, reverse=True) or
            [_make_od_pool("m5.large", 2, 8.0, 0.0300, self.available_azs[0], lifecycle="spot")]
        )[0]

        od_nodes,   _     = self._pack_ffd(stateful_pods, od_pool, 999, "od_stateful")

        # Spread control-plane pods round-robin across OD nodes (fallback mode)
        if _cp_pods:
            while len(od_nodes) < 2:
                od_nodes.append(PlacementNode(
                    pool=_pool_for_az(od_pool, self.available_azs, len(od_nodes)),
                    role="od_stateful",
                ))
            for idx, pod in enumerate(_cp_pods):
                n_count = len(od_nodes)
                placed = False
                for offset in range(n_count):
                    node = od_nodes[(idx + offset) % n_count]
                    if node.can_fit(pod):
                        node.assign(pod)
                        placed = True
                        break
                if not placed:
                    nn = PlacementNode(
                        pool=_pool_for_az(od_pool, self.available_azs, len(od_nodes)),
                        role="od_overflow",
                    )
                    nn.assign(pod)
                    od_nodes.append(nn)

        spot_nodes, unfit = self._pack_bfd_tsc(spot_pods, spot_pool, 999)

        for pod in sorted(
            unfit,
            key=lambda p: p.cpu_request_millicores + p.memory_request_mb * 0.5,
            reverse=True,
        ):
            placed = False
            for node in sorted(od_nodes, key=lambda n: n.cpu_free_millicores, reverse=True):
                if node.can_fit(pod):
                    node.assign(pod)
                    placed = True
                    break
            if not placed:
                nn = PlacementNode(
                    pool=_pool_for_az(od_pool, self.available_azs, len(od_nodes)),
                    role="od_overflow",
                )
                nn.assign(pod)
                od_nodes.append(nn)

        if not od_nodes:
            od_nodes = [PlacementNode(
                pool=_pool_for_az(od_pool, self.available_azs, 0), role="od_stateful",
            )]

        buffer_nodes: List[PlacementNode] = [
            PlacementNode(
                pool=_pool_for_az(spot_pool, self.available_azs, len(spot_nodes) + i),
                role="buffer",
            )
            for i in range(buffer_count)
        ]

        all_nodes = od_nodes + spot_nodes + buffer_nodes
        score, metrics = self._score_placement(all_nodes, spot_nodes)
        rec_cost    = sum(n.pool.hourly_cost * HOURS_PER_MONTH for n in all_nodes)
        savings     = max(0.0, current_monthly_cost - rec_cost)
        savings_pct = (savings / current_monthly_cost * 100) if current_monthly_cost > 0 else 0.0

        return PlacementResult(
            od_nodes=od_nodes, spot_nodes=spot_nodes, buffer_nodes=buffer_nodes,
            stateful_pods=len(stateful_pods), spot_friendly_pods=len(spot_pods),
            misplaced_pods=0,
            placement_score=score,
            current_monthly_cost=current_monthly_cost,
            recommended_monthly_cost=rec_cost,
            savings_monthly=savings, savings_pct=savings_pct,
            az_distribution=metrics["az_distribution"],
            family_distribution=metrics["family_distribution"],
            max_az_concentration_pct=metrics["max_az_concentration_pct"],
            max_family_concentration_pct=metrics["max_family_concentration_pct"],
            interruption_probability=metrics["interruption_probability"],
            warnings=warnings,
        )

    # ── Scoring helpers ────────────────────────────────────────────────────────

    def _az_diversity_ok(self, node: PlacementNode, all_spot: List[PlacementNode]) -> bool:
        az    = node.pool.az
        total = sum(len(n.assigned_pods) for n in all_spot) + 1
        az_ct = sum(len(n.assigned_pods) for n in all_spot if n.pool.az == az) + 1
        return (az_ct / total) <= MAX_AZ_RATIO if total else True

    def _score_placement(
        self,
        all_nodes:  List[PlacementNode],
        spot_nodes: List[PlacementNode],
    ) -> Tuple[float, dict]:
        if not all_nodes:
            return 0.0, {
                "az_distribution": {}, "family_distribution": {},
                "max_az_concentration_pct": 0, "max_family_concentration_pct": 0,
                "interruption_probability": 0,
            }
        az_d:  Dict[str, int] = {}
        fam_d: Dict[str, int] = {}
        for n in all_nodes:
            az_d[n.pool.az]      = az_d.get(n.pool.az, 0) + 1
            fam_d[n.pool.family] = fam_d.get(n.pool.family, 0) + 1
        t        = len(all_nodes)
        max_az   = max(az_d.values())  / t
        max_fam  = max(fam_d.values()) / t
        used_cpu = sum(n.cpu_used_millicores for n in all_nodes)
        cap_cpu  = sum(n.pool.cpu_capacity_millicores for n in all_nodes)
        avg_util = used_cpu / cap_cpu if cap_cpu else 0
        avg_int  = (
            sum(n.pool.interruption_probability for n in spot_nodes) / len(spot_nodes)
            if spot_nodes else 0
        )
        score = (1 - max_az) * 0.25 + (1 - max_fam) * 0.20 + avg_util * 0.25 - avg_int * 0.30
        return max(0.0, min(1.0, score)), {
            "az_distribution":              az_d,
            "family_distribution":          fam_d,
            "max_az_concentration_pct":     max_az  * 100,
            "max_family_concentration_pct": max_fam * 100,
            "interruption_probability":     avg_int,
        }


# ── Utility helpers ────────────────────────────────────────────────────────────

def _interruption_label(prob: float) -> str:
    if prob < 0.05:  return "Low (<5%)"
    if prob < 0.15:  return "Medium (5-15%)"
    if prob < 0.30:  return "High (15-30%)"
    return "Very High (>30%)"

def _make_od_pool(itype: str, vcpu: int, mem_gb: float, hourly: float, az: str,
                  lifecycle: str = "on-demand") -> PoolInfo:
    family = itype.split(".")[0] if "." in itype else itype
    return PoolInfo(instance_type=itype, az=az, family=family, lifecycle=lifecycle,
                    hourly_cost=hourly, interruption_probability=0.0, vcpu=vcpu, memory_gb=mem_gb)

def _pool_for_az(template: PoolInfo, azs: List[str], index: int) -> PoolInfo:
    az = azs[index % len(azs)] if azs else template.az
    return PoolInfo(instance_type=template.instance_type, az=az, family=template.family,
                    lifecycle=template.lifecycle, hourly_cost=template.hourly_cost,
                    interruption_probability=template.interruption_probability,
                    vcpu=template.vcpu, memory_gb=template.memory_gb)

def build_pools_from_rankings(rankings: List[dict], available_azs: List[str]) -> List[PoolInfo]:
    pools: List[PoolInfo] = []
    for r in rankings:
        it = r.get("instance_type", ""); az = r.get("az", "")
        if not it or not az: continue
        family    = it.split(".")[0] if "." in it else it
        lifecycle = "spot" if r.get("lifecycle","spot") == "spot" else "on-demand"
        pools.append(PoolInfo(
            instance_type=it, az=az, family=family, lifecycle=lifecycle,
            hourly_cost=float(r.get("hourly_cost",0.0)) or float(r.get("price_per_hour",0.0)),
            interruption_probability=float(r.get("risk_probability",0.0)),
            vcpu=int(r.get("vcpu",2)), memory_gb=float(r.get("memory_gb",4.0)),
        ))
    return pools

def pods_from_cluster_detail(nodes_detailed: List[dict]) -> List[PodSpec]:
    pods: List[PodSpec] = []; seen: set = set()
    for node in nodes_detailed:
        for pod in node.get("pods", []):
            pname = pod.get("pod_name","")
            if pname in seen: continue
            seen.add(pname)
            pods.append(PodSpec(
                pod_name=pname, namespace=pod.get("namespace","default"),
                cpu_request_millicores=int(pod.get("cpu_request_millicores") or 100),
                memory_request_mb=float(pod.get("memory_request_mb") or 128),
                is_stateful_by_nature=(
                    pod.get("stateful_reason") == "by_nature"
                    or (pod.get("is_stateful",False) and pod.get("stateful_reason") != "by_placement")
                ),
                controller_kind=pod.get("controller_type","Deployment"),
                is_daemonset=pod.get("is_daemonset", False),
                is_control_plane=pod.get("is_control_plane", False),
            ))
    return pods
