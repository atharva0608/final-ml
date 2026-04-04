"""
Karpenter Simulation Engine v2 — Multi-Cycle Convergence
=========================================================

Replaces the single-pass FFD bin-packing with a production-grade simulation
that mirrors real Karpenter + auto-rebalancer behavior:

- Consistent snapshot (frozen timestamp)
- Virtual cluster state with node/pod transitions
- Multi-cycle convergence loop (max 10 cycles)
- Greedy scheduler (not globally-optimal FFD)
- Redis constraint replay (launch_blocked, blacklist, risky_pools)
- Per-cluster pool view (not shared regional cache)
- Stateless/stateful two-pool separation
- Fragmentation modeling (8% default correction)
- Confidence scoring

Source spec: documents/changes.md (Stages 1-9)
"""

from __future__ import annotations

import re
import uuid
import math
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("spot.simulation_engine")

# ─── Constants ────────────────────────────────────────────────────────────────
TICK_SECONDS = 30
PROVISIONING_TICKS = 3       # ~90s average Karpenter node join
STABILIZATION_TICKS = 3      # ~90s post-join stabilization
DRAIN_TICKS_PER_NODE = 1     # ~30s per node drain fast path
MAX_SIMULATION_TICKS = 30    # 15-minute cap
MAX_CYCLES = 10
FRAGMENTATION_PCT = 0.08     # 8% default correction factor
KUBELET_CPU_M = 100
KUBELET_MEM_BYTES = 256 * 1024 * 1024
SYSTEM_NAMESPACES = frozenset({'kube-system', 'kube-public', 'kube-node-lease'})
DAEMONSET_KINDS = frozenset({'DaemonSet', 'daemonset'})
ENGINE_VERSION = "v2-convergence"


# ─── Stage 1: Simulation Snapshot ─────────────────────────────────────────────

@dataclass
class SimNode:
    instance_id: str
    instance_type: str
    lifecycle: str               # "spot" | "on-demand"
    az: str
    architecture: str            # "amd64" | "arm64"
    vcpu: int
    memory_gb: float
    price_hourly: float
    workload_class: str          # "stateless" | "stateful" | "system"
    status: str                  # "READY" | "CALIBRATING" | "UNKNOWN"
    is_standby: bool
    node_name: str = ""


@dataclass
class SimPod:
    pod_name: str
    namespace: str
    controller_name: str
    controller_kind: str
    cpu_millicores: int
    memory_bytes: int
    is_stateful: bool
    is_daemonset: bool
    is_system: bool
    node_name: str = ""
    # Scheduling constraints (populated from pod_metadata)
    node_selector: Optional[Dict[str, str]] = None
    tolerations: Optional[List[Dict[str, str]]] = None
    has_pod_anti_affinity: bool = False
    has_pod_affinity: bool = False
    topology_spread_constraints: Optional[List[Dict[str, Any]]] = None
    # Resource limits for headroom calculation
    cpu_limit_millicores: Optional[int] = None
    memory_limit_bytes: Optional[int] = None


@dataclass
class SimRedisState:
    launch_blocked: Set[str] = field(default_factory=set)
    blacklisted_pools: Set[str] = field(default_factory=set)
    risky_pools: Set[str] = field(default_factory=set)
    pdb_safe_percent: Optional[int] = None


@dataclass
class SimClusterSettings:
    target_spot_exposure_pct: int = 100
    diversify_pools: bool = False
    max_family_diversification_cap_pct: int = 40
    architecture_preference: str = "both"
    min_node_count: int = 1
    rebalance_batch_percent: Optional[int] = None
    risk_ceiling_percent: int = 25
    risk_savings_tradeoff_pct: int = 20


@dataclass
class SimPool:
    instance_type: str
    az: str
    architecture: str
    vcpu: int
    memory_gb: float
    spot_price: float
    od_price: float
    risk_probability: float
    ml_score: float
    allocatable_cpu_m: int = 0
    allocatable_mem_bytes: int = 0


@dataclass
class SimulationSnapshot:
    snapshot_id: str
    frozen_at: datetime
    cluster_id: str
    nodes: List[SimNode]
    pods: List[SimPod]
    redis_state: SimRedisState
    cluster_settings: SimClusterSettings
    karpenter_mode: str
    use_rightsized: bool
    candidate_pools: List[SimPool]
    ds_cpu_overhead: int = 0
    ds_mem_overhead: int = 0
    is_valid: bool = True
    invalid_reason: Optional[str] = None


# ─── Stage 2: Virtual Cluster State ──────────────────────────────────────────

@dataclass
class VirtualNode:
    node_id: str
    instance_type: str
    lifecycle: str
    az: str
    architecture: str
    vcpu: int
    memory_gb: float
    price_hourly: float
    workload_class: str
    status: str                  # READY / CORDONED / DRAINING / PROVISIONING / STABILIZING / TERMINATED
    allocatable_cpu_m: int = 0
    allocatable_mem_bytes: int = 0
    used_cpu_m: int = 0
    used_mem_bytes: int = 0
    provisioning_ticks_remaining: int = 0
    stabilization_ticks_remaining: int = 0
    is_new_this_cycle: bool = False
    # Node labels for nodeSelector matching (auto-derived from instance properties)
    labels: Dict[str, str] = field(default_factory=dict)
    # Node taints for toleration matching
    taints: List[Dict[str, str]] = field(default_factory=list)

    def remaining_cpu(self) -> int:
        return self.allocatable_cpu_m - self.used_cpu_m

    def remaining_mem(self) -> int:
        return self.allocatable_mem_bytes - self.used_mem_bytes

    def tick(self):
        if self.status == 'PROVISIONING':
            self.provisioning_ticks_remaining -= 1
            if self.provisioning_ticks_remaining <= 0:
                self.status = 'STABILIZING'
                self.stabilization_ticks_remaining = STABILIZATION_TICKS
        elif self.status == 'STABILIZING':
            self.stabilization_ticks_remaining -= 1
            if self.stabilization_ticks_remaining <= 0:
                self.status = 'READY'
                self.is_new_this_cycle = True


@dataclass
class VirtualPod:
    pod_id: str
    pod_name: str
    namespace: str
    controller_name: str
    controller_kind: str
    cpu_millicores: int
    memory_bytes: int
    is_stateful: bool
    is_daemonset: bool
    is_system: bool
    node_id: Optional[str] = None
    status: str = "RUNNING"     # RUNNING / PENDING / FAILED
    # Scheduling constraints
    node_selector: Optional[Dict[str, str]] = None
    tolerations: Optional[List[Dict[str, str]]] = None
    has_pod_anti_affinity: bool = False
    has_pod_affinity: bool = False
    topology_spread_constraints: Optional[List[Dict[str, Any]]] = None
    cpu_limit_millicores: Optional[int] = None
    memory_limit_bytes: Optional[int] = None


def _derive_node_labels(instance_type: str, architecture: str, az: str) -> Dict[str, str]:
    """Derive standard K8s/Karpenter node labels from instance properties."""
    return {
        'kubernetes.io/arch': architecture or 'amd64',
        'kubernetes.io/os': 'linux',
        'node.kubernetes.io/instance-type': instance_type,
        'topology.kubernetes.io/zone': az or '',
        'karpenter.sh/capacity-type': 'spot',  # all sim nodes are spot candidates
    }


def _derive_node_taints(lifecycle: str) -> List[Dict[str, str]]:
    """Derive node taints based on lifecycle (spot nodes get a taint)."""
    taints = []
    if lifecycle == 'spot':
        taints.append({
            'key': 'karpenter.sh/lifecycle',
            'value': 'spot',
            'effect': 'NoSchedule',
        })
    return taints


def _toleration_matches_taint(toleration: Dict[str, str], taint: Dict[str, str]) -> bool:
    """Check if a single toleration matches a single taint (K8s semantics)."""
    tol_key = toleration.get('key', '')
    tol_op = toleration.get('operator', 'Equal')
    tol_value = toleration.get('value', '')
    tol_effect = toleration.get('effect', '')

    # Operator 'Exists' matches any taint with that key (and optionally effect)
    if tol_op == 'Exists':
        if tol_key == '':
            return True  # empty key + Exists = tolerate everything
        if tol_key != taint.get('key', ''):
            return False
        if tol_effect and tol_effect != taint.get('effect', ''):
            return False
        return True

    # Operator 'Equal' (default)
    if tol_key != taint.get('key', ''):
        return False
    if tol_value != taint.get('value', ''):
        return False
    if tol_effect and tol_effect != taint.get('effect', ''):
        return False
    return True


class VirtualClusterState:
    """Tracks virtual cluster state across simulation cycles."""

    def __init__(self):
        self.nodes: Dict[str, VirtualNode] = {}
        self.pods: Dict[str, VirtualPod] = {}
        self.cycle: int = 0
        self.total_provisioning_failures: int = 0
        self.peak_pending_pods: int = 0
        self.pools_skipped_launch_blocked: int = 0
        self.pools_skipped_blacklisted: int = 0

    @classmethod
    def from_snapshot(cls, snapshot: SimulationSnapshot) -> VirtualClusterState:
        state = cls()
        ds_cpu = snapshot.ds_cpu_overhead + KUBELET_CPU_M
        ds_mem = snapshot.ds_mem_overhead + KUBELET_MEM_BYTES

        for sn in snapshot.nodes:
            alloc_cpu = int(sn.vcpu * 1000 * 0.95) - ds_cpu
            alloc_mem = int(sn.memory_gb * 1024 * 1024 * 1024 * 0.95) - ds_mem
            vn = VirtualNode(
                node_id=sn.instance_id,
                instance_type=sn.instance_type,
                lifecycle=sn.lifecycle,
                az=sn.az,
                architecture=sn.architecture,
                vcpu=sn.vcpu,
                memory_gb=sn.memory_gb,
                price_hourly=sn.price_hourly,
                workload_class=sn.workload_class,
                status='READY' if sn.status == 'READY' else sn.status,
                allocatable_cpu_m=max(0, alloc_cpu),
                allocatable_mem_bytes=max(0, alloc_mem),
                labels=_derive_node_labels(sn.instance_type, sn.architecture, sn.az),
                taints=_derive_node_taints(sn.lifecycle),
            )
            state.nodes[vn.node_id] = vn

        for sp in snapshot.pods:
            if sp.is_daemonset or sp.is_system:
                continue  # DaemonSets are overhead, not scheduled
            vp = VirtualPod(
                pod_id=f"{sp.namespace}/{sp.pod_name}",
                pod_name=sp.pod_name,
                namespace=sp.namespace,
                controller_name=sp.controller_name,
                controller_kind=sp.controller_kind,
                cpu_millicores=sp.cpu_millicores,
                memory_bytes=sp.memory_bytes,
                is_stateful=sp.is_stateful,
                is_daemonset=False,
                is_system=False,
                node_id=None,
                status='RUNNING',
                node_selector=sp.node_selector,
                tolerations=sp.tolerations,
                has_pod_anti_affinity=sp.has_pod_anti_affinity,
                has_pod_affinity=sp.has_pod_affinity,
                topology_spread_constraints=sp.topology_spread_constraints,
                cpu_limit_millicores=sp.cpu_limit_millicores,
                memory_limit_bytes=sp.memory_limit_bytes,
            )
            # Assign pod to its node if the node exists
            for nid, vn in state.nodes.items():
                if sp.node_name and sp.node_name == getattr(state.nodes.get(nid), 'node_id', ''):
                    vp.node_id = nid
                    vn.used_cpu_m += sp.cpu_millicores
                    vn.used_mem_bytes += sp.memory_bytes
                    break
            else:
                # Pod not matched to a node — set as running on first available
                # (best effort; snapshot should have node_name)
                if sp.node_name:
                    for nid, vn in state.nodes.items():
                        vp.node_id = nid
                        vn.used_cpu_m += sp.cpu_millicores
                        vn.used_mem_bytes += sp.memory_bytes
                        break

            state.pods[vp.pod_id] = vp

        return state

    def ready_nodes(self) -> List[VirtualNode]:
        return [n for n in self.nodes.values() if n.status == 'READY']

    def ready_nodes_sorted_by_remaining_cpu_desc(self) -> List[VirtualNode]:
        return sorted(self.ready_nodes(), key=lambda n: -n.remaining_cpu())

    def new_ready_nodes(self) -> List[VirtualNode]:
        return [n for n in self.nodes.values()
                if n.status == 'READY' and n.is_new_this_cycle]

    def provisioning_nodes(self) -> List[VirtualNode]:
        return [n for n in self.nodes.values()
                if n.status in ('PROVISIONING', 'STABILIZING')]

    def get_running_pods(self, node_id: str) -> List[VirtualPod]:
        return [p for p in self.pods.values()
                if p.node_id == node_id and p.status == 'RUNNING']

    def get_pending_pods(self) -> List[VirtualPod]:
        return [p for p in self.pods.values() if p.status == 'PENDING']

    def spot_node_count(self) -> int:
        return sum(1 for n in self.nodes.values()
                   if n.status == 'READY' and n.lifecycle == 'spot')

    def total_running_node_count(self) -> int:
        return sum(1 for n in self.nodes.values()
                   if n.status in ('READY', 'CORDONED', 'DRAINING'))

    def count_nodes_by_family(self, family: str) -> int:
        return sum(1 for n in self.nodes.values()
                   if n.status == 'READY' and n.instance_type.split('.')[0] == family)

    def count_nodes_by_az(self, az: str) -> int:
        return sum(1 for n in self.nodes.values()
                   if n.status == 'READY' and n.az == az)

    def cordon_node(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id].status = 'CORDONED'

    def drain_node(self, node_id: str) -> List[str]:
        """Mark node draining; move its pods to PENDING."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        node.status = 'DRAINING'
        evicted_ids = []
        for pid, pod in self.pods.items():
            if pod.node_id == node_id and pod.status == 'RUNNING':
                pod.status = 'PENDING'
                pod.node_id = None
                evicted_ids.append(pid)
        node.used_cpu_m = 0
        node.used_mem_bytes = 0
        return evicted_ids

    def terminate_node(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id].status = 'TERMINATED'

    def provision_node(self, pool: SimPool, ds_cpu: int, ds_mem: int) -> str:
        """Add a new node in PROVISIONING state."""
        vnode_id = f"sim-{uuid.uuid4().hex[:8]}"
        alloc_cpu = int(pool.vcpu * 1000 * 0.95) - ds_cpu
        alloc_mem = int(pool.memory_gb * 1024 * 1024 * 1024 * 0.95) - ds_mem
        vn = VirtualNode(
            node_id=vnode_id,
            instance_type=pool.instance_type,
            lifecycle='spot',
            az=pool.az,
            architecture=pool.architecture,
            vcpu=pool.vcpu,
            memory_gb=pool.memory_gb,
            price_hourly=pool.spot_price,
            workload_class='stateless',
            status='PROVISIONING',
            allocatable_cpu_m=max(0, alloc_cpu),
            allocatable_mem_bytes=max(0, alloc_mem),
            provisioning_ticks_remaining=PROVISIONING_TICKS,
            labels=_derive_node_labels(pool.instance_type, pool.architecture, pool.az),
            taints=_derive_node_taints('spot'),
        )
        self.nodes[vnode_id] = vn
        return vnode_id

    def place_pod(self, pod_id: str, node_id: str):
        pod = self.pods.get(pod_id)
        node = self.nodes.get(node_id)
        if pod and node:
            pod.status = 'RUNNING'
            pod.node_id = node_id
            node.used_cpu_m += pod.cpu_millicores
            node.used_mem_bytes += pod.memory_bytes

    def tick_provisioning_nodes(self):
        for node in self.nodes.values():
            node.tick()

    def reset_new_flags(self):
        for node in self.nodes.values():
            node.is_new_this_cycle = False

    def check_convergence(self) -> bool:
        no_pending = len(self.get_pending_pods()) == 0
        no_provisioning = len(self.provisioning_nodes()) == 0
        return no_pending and no_provisioning


# ─── Stage 6: Constraint Replay Engine ────────────────────────────────────────

def is_pool_eligible(pool: SimPool, redis_state: SimRedisState,
                     cluster_id: str) -> Tuple[bool, str]:
    pool_key = f"{pool.instance_type}:{pool.az}"
    blocked_key = f"{cluster_id}:{pool.instance_type}:{pool.az}"

    if blocked_key in redis_state.launch_blocked:
        return False, "launch_blocked"
    if pool_key in redis_state.blacklisted_pools:
        return False, "globally_blacklisted"
    if pool_key in redis_state.risky_pools:
        return False, "risky_pool"
    return True, "eligible"


def apply_diversification(pool: SimPool, state: VirtualClusterState,
                          settings: SimClusterSettings) -> bool:
    if not settings.diversify_pools:
        return True
    total = state.total_running_node_count()
    if total == 0:
        return True
    family = pool.instance_type.split('.')[0]
    family_count = state.count_nodes_by_family(family)
    family_cap = settings.max_family_diversification_cap_pct / 100
    if family_count / max(total, 1) >= family_cap:
        return False
    az_count = state.count_nodes_by_az(pool.az)
    if az_count / max(total, 1) >= 0.50:
        return False
    return True


# ─── Stage 7: Per-Cluster Pool View ──────────────────────────────────────────

def build_cluster_pool_view(
    candidate_pools: List[SimPool],
    redis_state: SimRedisState,
    cluster_id: str,
    cluster_azs: Set[str],
    settings: SimClusterSettings,
) -> List[SimPool]:
    """Filter pools to cluster-specific eligible set."""
    eligible = []
    skipped_blocked = 0
    skipped_blacklisted = 0

    for pool in candidate_pools:
        # AZ filter
        if cluster_azs and pool.az not in cluster_azs:
            continue

        # Architecture filter
        arch_pref = settings.architecture_preference
        if arch_pref != "both" and pool.architecture != arch_pref:
            continue

        # Constraint replay
        ok, reason = is_pool_eligible(pool, redis_state, cluster_id)
        if not ok:
            if reason == "launch_blocked":
                skipped_blocked += 1
            else:
                skipped_blacklisted += 1
            continue

        eligible.append(pool)

    eligible.sort(key=lambda p: (p.spot_price, -p.ml_score))
    return eligible, skipped_blocked, skipped_blacklisted


# ─── Stage 3: Multi-Cycle Convergence Loop ────────────────────────────────────

@dataclass
class CycleResult:
    cycle: int
    candidates_selected: int
    pods_evicted: int
    nodes_provisioned: int
    provisioning_failures: int
    pods_placed: int
    pods_unschedulable: int
    nodes_terminated: int


@dataclass
class SimulationResult:
    cycles_run: int
    converged: bool
    timed_out: bool
    final_state: VirtualClusterState
    history: List[CycleResult]
    confidence_score: float
    snapshot_frozen_at: datetime
    pod_data_age_seconds: int


def select_pool_for_pending(
    pending_pods: List[VirtualPod],
    eligible_pools: List[SimPool],
    state: VirtualClusterState,
    settings: SimClusterSettings,
) -> Optional[SimPool]:
    """Select best pool for a batch of pending pods using the 4-pass algorithm."""
    if not pending_pods or not eligible_pools:
        return None

    min_cpu_m = max(p.cpu_millicores for p in pending_pods)
    min_mem_b = max(p.memory_bytes for p in pending_pods)
    risk_ceiling = settings.risk_ceiling_percent / 100

    # Pass 1: VALUE + SAFETY
    for pool in eligible_pools:
        if pool.allocatable_cpu_m >= min_cpu_m and pool.allocatable_mem_bytes >= min_mem_b:
            if pool.risk_probability < risk_ceiling and pool.spot_price < pool.od_price:
                if apply_diversification(pool, state, settings):
                    return pool

    # Pass 2: Allow slightly costlier if safer
    tradeoff = settings.risk_savings_tradeoff_pct / 100
    cheapest_price = min((p.spot_price for p in eligible_pools if p.allocatable_cpu_m >= min_cpu_m), default=0)
    for pool in eligible_pools:
        if pool.allocatable_cpu_m >= min_cpu_m and pool.allocatable_mem_bytes >= min_mem_b:
            if pool.risk_probability < risk_ceiling:
                price_ok = pool.spot_price <= cheapest_price + tradeoff * (pool.od_price - cheapest_price)
                if price_ok:
                    return pool

    # Pass 3: Risk override — any pool safer than worst current
    for pool in eligible_pools:
        if pool.allocatable_cpu_m >= min_cpu_m and pool.allocatable_mem_bytes >= min_mem_b:
            if pool.risk_probability < risk_ceiling:
                return pool

    # Pass 4: Final fallback — anything cheaper than OD
    for pool in eligible_pools:
        if pool.allocatable_cpu_m >= min_cpu_m and pool.allocatable_mem_bytes >= min_mem_b:
            if pool.spot_price < pool.od_price:
                return pool

    return None


def node_fits_pod(node: VirtualNode, pod: VirtualPod) -> bool:
    cpu_eff = pod.cpu_millicores
    mem_eff = pod.memory_bytes
    # Resource limit headroom: if limit >> request, real usage may exceed request
    # Apply 20% headroom when limit is more than 2x the request
    if pod.cpu_limit_millicores and pod.cpu_limit_millicores > cpu_eff * 2:
        cpu_eff = int(cpu_eff * 1.2)
    if pod.memory_limit_bytes and pod.memory_limit_bytes > mem_eff * 2:
        mem_eff = int(mem_eff * 1.2)
    return (cpu_eff <= node.remaining_cpu() and
            mem_eff <= node.remaining_mem())


def node_allows_pod(node: VirtualNode, pod: VirtualPod) -> bool:
    if node.status != 'READY':
        return False
    # Stateful pods only on stateful/system nodes
    if pod.is_stateful and node.workload_class not in ('stateful', 'system'):
        return False
    # Non-stateful pods only on stateless nodes
    if not pod.is_stateful and node.workload_class not in ('stateless',):
        return False

    # ── nodeSelector enforcement ──
    if pod.node_selector:
        for key, val in pod.node_selector.items():
            if node.labels.get(key) != val:
                return False

    # ── Taint/Toleration enforcement ──
    if node.taints:
        pod_tolerations = pod.tolerations or []
        for taint in node.taints:
            tolerated = any(
                _toleration_matches_taint(tol, taint)
                for tol in pod_tolerations
            )
            if not tolerated:
                return False

    return True


def run_simulation(snapshot: SimulationSnapshot) -> SimulationResult:
    """Main entry: multi-cycle convergence simulation."""
    if not snapshot.is_valid:
        logger.warning(f"Snapshot invalid: {snapshot.invalid_reason}")
        return _empty_result(snapshot)

    state = VirtualClusterState.from_snapshot(snapshot)
    ds_overhead_cpu = snapshot.ds_cpu_overhead + KUBELET_CPU_M
    ds_overhead_mem = snapshot.ds_mem_overhead + KUBELET_MEM_BYTES

    cluster_azs = {n.az for n in snapshot.nodes}
    eligible_pools, skipped_blocked, skipped_blacklisted = build_cluster_pool_view(
        snapshot.candidate_pools,
        snapshot.redis_state,
        snapshot.cluster_id,
        cluster_azs,
        snapshot.cluster_settings,
    )

    state.pools_skipped_launch_blocked = skipped_blocked
    state.pools_skipped_blacklisted = skipped_blacklisted

    # Compute allocatable for each eligible pool
    for pool in eligible_pools:
        pool.allocatable_cpu_m = int(pool.vcpu * 1000 * 0.95) - ds_overhead_cpu
        pool.allocatable_mem_bytes = int(pool.memory_gb * 1024 * 1024 * 1024 * 0.95) - ds_overhead_mem

    eligible_pools = [p for p in eligible_pools
                      if p.allocatable_cpu_m > 0 and p.allocatable_mem_bytes > 0]

    history: List[CycleResult] = []
    settings = snapshot.cluster_settings
    total_ticks = 0
    timed_out = False

    for cycle_num in range(MAX_CYCLES):
        state.cycle = cycle_num
        state.reset_new_flags()
        prev_node_count = len([n for n in state.nodes.values()
                               if n.status not in ('TERMINATED',)])

        # ── Step 1: Select consolidation candidates ──
        candidates = _select_candidates(state, settings)

        if not candidates and state.check_convergence():
            history.append(CycleResult(
                cycle=cycle_num, candidates_selected=0, pods_evicted=0,
                nodes_provisioned=0, provisioning_failures=0,
                pods_placed=0, pods_unschedulable=0, nodes_terminated=0
            ))
            break

        # ── Step 2: Drain candidates ──
        total_evicted = 0
        nodes_terminated = 0
        for node in candidates:
            evicted_ids = state.drain_node(node.node_id)
            total_evicted += len(evicted_ids)
            state.terminate_node(node.node_id)
            nodes_terminated += 1

        # Update peak pending
        pending = state.get_pending_pods()
        if len(pending) > state.peak_pending_pods:
            state.peak_pending_pods = len(pending)

        # ── Step 3: Karpenter provisioning ──
        nodes_provisioned = 0
        prov_failures = 0
        if pending:
            # Group pending pods by resource needs (simple batching)
            groups = _batch_pending_pods(pending)
            for group in groups:
                pool = select_pool_for_pending(group, eligible_pools, state, settings)
                if pool:
                    state.provision_node(pool, ds_overhead_cpu, ds_overhead_mem)
                    nodes_provisioned += 1
                else:
                    prov_failures += 1
                    state.total_provisioning_failures += 1

        # ── Tick provisioning timers until nodes become READY ──
        tick_budget = PROVISIONING_TICKS + STABILIZATION_TICKS + 2
        for _ in range(tick_budget):
            if total_ticks >= MAX_SIMULATION_TICKS:
                timed_out = True
                break
            state.tick_provisioning_nodes()
            total_ticks += 1
            if not state.provisioning_nodes():
                break

        if timed_out:
            history.append(CycleResult(
                cycle=cycle_num, candidates_selected=len(candidates),
                pods_evicted=total_evicted, nodes_provisioned=nodes_provisioned,
                provisioning_failures=prov_failures, pods_placed=0,
                pods_unschedulable=len(pending), nodes_terminated=nodes_terminated
            ))
            break

        # ── Step 4: Scheduler placement (greedy, not global FFD) ──
        placed, unschedulable = _simulate_scheduler(state)

        # Track peak pending
        current_pending = len(state.get_pending_pods())
        if current_pending > state.peak_pending_pods:
            state.peak_pending_pods = current_pending

        history.append(CycleResult(
            cycle=cycle_num,
            candidates_selected=len(candidates),
            pods_evicted=total_evicted,
            nodes_provisioned=nodes_provisioned,
            provisioning_failures=prov_failures,
            pods_placed=placed,
            pods_unschedulable=unschedulable,
            nodes_terminated=nodes_terminated,
        ))

        # ── Step 5: Convergence check ──
        if not candidates and state.check_convergence():
            break

    # ── Fragmentation correction ──
    _apply_fragmentation_correction(state, eligible_pools, ds_overhead_cpu, ds_overhead_mem)

    # ── HA constraint ──
    _enforce_ha_minimum(state, eligible_pools, ds_overhead_cpu, ds_overhead_mem, settings)

    # ── Confidence score ──
    confidence = _compute_confidence(snapshot, state, history)

    return SimulationResult(
        cycles_run=len(history),
        converged=state.check_convergence(),
        timed_out=timed_out,
        final_state=state,
        history=history,
        confidence_score=confidence,
        snapshot_frozen_at=snapshot.frozen_at,
        pod_data_age_seconds=0,  # caller computes from snapshot freshness
    )


def _select_candidates(state: VirtualClusterState,
                       settings: SimClusterSettings) -> List[VirtualNode]:
    """Identify nodes eligible for consolidation (stateless OD + risky spot)."""
    candidates = []
    for node in state.ready_nodes():
        if node.workload_class in ('stateful', 'system'):
            continue
        if node.lifecycle == 'on-demand':
            candidates.append(node)

    # Apply spot exposure cap
    candidates = _apply_spot_exposure_cap(candidates, state, settings)

    # Apply PDB-safe batch sizing
    pdb_pct = state.pods  # placeholder; use settings
    batch_pct = settings.rebalance_batch_percent
    if batch_pct is None:
        batch_pct = 15  # default
    batch_size = max(1, int(len(candidates) * batch_pct / 100))
    candidates = candidates[:batch_size]

    return candidates


def _apply_spot_exposure_cap(
    candidates: List[VirtualNode],
    state: VirtualClusterState,
    settings: SimClusterSettings,
) -> List[VirtualNode]:
    target = settings.target_spot_exposure_pct
    if target == 100:
        return candidates

    current_spot = state.spot_node_count()
    total = state.total_running_node_count()
    current_spot_pct = (current_spot / total * 100) if total > 0 else 0

    if current_spot_pct >= target:
        return []

    od_to_convert = max(1, int((target - current_spot_pct) / 100 * total))
    return candidates[:od_to_convert]


def _batch_pending_pods(pending: List[VirtualPod]) -> List[List[VirtualPod]]:
    """Group pending pods by compatible resource profiles for Karpenter batching."""
    if not pending:
        return []

    # Simple grouping: sort by CPU descending, batch up to ~4 pods per group
    sorted_pods = sorted(pending, key=lambda p: -p.cpu_millicores)
    groups = []
    batch = []
    for pod in sorted_pods:
        batch.append(pod)
        if len(batch) >= 4:
            groups.append(batch)
            batch = []
    if batch:
        groups.append(batch)
    return groups


def _simulate_scheduler(state: VirtualClusterState) -> Tuple[int, int]:
    """Greedy scheduler — mirrors real K8s behavior with constraint enforcement."""
    pending = state.get_pending_pods()
    placed_count = 0
    unschedulable_count = 0

    # Build controller→node mapping for anti-affinity checks
    controller_node_map: Dict[str, Set[str]] = {}
    for p in state.pods.values():
        if p.status == 'RUNNING' and p.node_id and p.controller_name:
            key = f"{p.namespace}/{p.controller_name}"
            controller_node_map.setdefault(key, set()).add(p.node_id)

    # Build topology spread tracking: (topology_key, controller_key) → {topology_value: count}
    topo_spread_counts: Dict[Tuple[str, str], Dict[str, int]] = {}
    for p in state.pods.values():
        if p.status == 'RUNNING' and p.node_id and p.controller_name:
            ctrl_key = f"{p.namespace}/{p.controller_name}"
            node = state.nodes.get(p.node_id)
            if node and p.topology_spread_constraints:
                for tsc in p.topology_spread_constraints:
                    topo_key = tsc.get('topology_key', '')
                    if not topo_key:
                        continue
                    map_key = (topo_key, ctrl_key)
                    topo_val = node.labels.get(topo_key, '')
                    topo_spread_counts.setdefault(map_key, {})
                    topo_spread_counts[map_key][topo_val] = topo_spread_counts[map_key].get(topo_val, 0) + 1

    for pod in pending:
        placed = False
        ctrl_key = f"{pod.namespace}/{pod.controller_name}" if pod.controller_name else None

        # Try existing READY nodes (most remaining CPU first)
        for node in state.ready_nodes_sorted_by_remaining_cpu_desc():
            if not node_fits_pod(node, pod) or not node_allows_pod(node, pod):
                continue

            # ── Pod anti-affinity enforcement ──
            if pod.has_pod_anti_affinity and ctrl_key:
                existing_nodes = controller_node_map.get(ctrl_key, set())
                if node.node_id in existing_nodes:
                    continue  # same controller already has a pod on this node

            # ── Topology spread constraint enforcement ──
            if pod.topology_spread_constraints and ctrl_key:
                spread_ok = _check_topology_spread(
                    node, pod, ctrl_key, topo_spread_counts, state
                )
                if not spread_ok:
                    continue

            state.place_pod(pod.pod_id, node.node_id)
            placed = True
            placed_count += 1
            # Update tracking maps
            if ctrl_key:
                controller_node_map.setdefault(ctrl_key, set()).add(node.node_id)
                if pod.topology_spread_constraints:
                    for tsc in pod.topology_spread_constraints:
                        topo_key = tsc.get('topology_key', '')
                        if topo_key:
                            map_key = (topo_key, ctrl_key)
                            topo_val = node.labels.get(topo_key, '')
                            topo_spread_counts.setdefault(map_key, {})
                            topo_spread_counts[map_key][topo_val] = topo_spread_counts[map_key].get(topo_val, 0) + 1
            break

        if not placed:
            # Try newly provisioned READY nodes
            for node in state.new_ready_nodes():
                if not node_fits_pod(node, pod) or not node_allows_pod(node, pod):
                    continue

                if pod.has_pod_anti_affinity and ctrl_key:
                    if node.node_id in controller_node_map.get(ctrl_key, set()):
                        continue

                if pod.topology_spread_constraints and ctrl_key:
                    if not _check_topology_spread(node, pod, ctrl_key, topo_spread_counts, state):
                        continue

                state.place_pod(pod.pod_id, node.node_id)
                placed = True
                placed_count += 1
                if ctrl_key:
                    controller_node_map.setdefault(ctrl_key, set()).add(node.node_id)
                    if pod.topology_spread_constraints:
                        for tsc in pod.topology_spread_constraints:
                            topo_key = tsc.get('topology_key', '')
                            if topo_key:
                                map_key = (topo_key, ctrl_key)
                                topo_val = node.labels.get(topo_key, '')
                                topo_spread_counts.setdefault(map_key, {})
                                topo_spread_counts[map_key][topo_val] = topo_spread_counts[map_key].get(topo_val, 0) + 1
                break

        if not placed:
            pod.status = 'FAILED'
            unschedulable_count += 1

    return placed_count, unschedulable_count


def _check_topology_spread(
    node: VirtualNode,
    pod: VirtualPod,
    ctrl_key: str,
    topo_spread_counts: Dict[Tuple[str, str], Dict[str, int]],
    state: VirtualClusterState,
) -> bool:
    """Check if placing pod on node would violate topology spread constraints."""
    for tsc in (pod.topology_spread_constraints or []):
        max_skew = tsc.get('max_skew', 1)
        topo_key = tsc.get('topology_key', '')
        when_unsatisfiable = tsc.get('when_unsatisfiable', 'DoNotSchedule')

        if not topo_key or when_unsatisfiable != 'DoNotSchedule':
            continue  # ScheduleAnyway doesn't block placement

        topo_val = node.labels.get(topo_key, '')
        map_key = (topo_key, ctrl_key)
        counts = topo_spread_counts.get(map_key, {})

        # Count after hypothetical placement
        current_count = counts.get(topo_val, 0)
        hypothetical = current_count + 1

        # Find minimum count across all known topology values
        # Include AZs from all ready nodes to ensure we consider empty domains
        all_topo_vals = {n.labels.get(topo_key, '') for n in state.ready_nodes() if topo_key in n.labels}
        all_topo_vals.add(topo_val)

        min_count = min(counts.get(tv, 0) for tv in all_topo_vals) if all_topo_vals else 0

        if hypothetical - min_count > max_skew:
            return False

    return True


def _apply_fragmentation_correction(
    state: VirtualClusterState,
    eligible_pools: List[SimPool],
    ds_cpu: int,
    ds_mem: int,
):
    """Add fragmentation node if packing is too optimal."""
    ready_stateless = [n for n in state.nodes.values()
                       if n.status == 'READY' and n.workload_class == 'stateless']
    if not ready_stateless or not eligible_pools:
        return

    total_alloc = sum(n.allocatable_cpu_m for n in ready_stateless)
    total_used = sum(n.used_cpu_m for n in ready_stateless)
    if total_alloc == 0:
        return

    utilization = total_used / total_alloc
    waste = 1.0 - utilization
    if waste < FRAGMENTATION_PCT:
        # Packing is suspiciously optimal — add a fragmentation node
        # Use the most commonly selected instance type
        type_counts: Dict[str, int] = {}
        for n in ready_stateless:
            type_counts[n.instance_type] = type_counts.get(n.instance_type, 0) + 1
        most_common_type = max(type_counts, key=type_counts.get)

        for pool in eligible_pools:
            if pool.instance_type == most_common_type:
                state.provision_node(pool, ds_cpu, ds_mem)
                # Immediately make it ready
                new_node = list(state.nodes.values())[-1]
                new_node.status = 'READY'
                new_node.provisioning_ticks_remaining = 0
                break


def _enforce_ha_minimum(
    state: VirtualClusterState,
    eligible_pools: List[SimPool],
    ds_cpu: int,
    ds_mem: int,
    settings: SimClusterSettings,
):
    """Ensure minimum 2 stateless spot nodes for HA."""
    ready_stateless = [n for n in state.nodes.values()
                       if n.status == 'READY' and n.workload_class == 'stateless']
    min_nodes = min(2, settings.min_node_count) if settings.min_node_count > 0 else 2

    while len(ready_stateless) < min_nodes and eligible_pools:
        pool = eligible_pools[0]
        vid = state.provision_node(pool, ds_cpu, ds_mem)
        node = state.nodes[vid]
        node.status = 'READY'
        node.provisioning_ticks_remaining = 0
        ready_stateless.append(node)


def _compute_confidence(
    snapshot: SimulationSnapshot,
    state: VirtualClusterState,
    history: List[CycleResult],
) -> float:
    score = 1.0

    # Penalize stale pod metrics (caller should set pod_data_age)
    # For now, assume fresh if snapshot is valid

    # Penalize provisioning failures
    score -= 0.05 * state.total_provisioning_failures

    # Penalize unschedulable pods
    total_pods = len(state.pods)
    if total_pods > 0:
        failed = sum(1 for p in state.pods.values() if p.status == 'FAILED')
        score -= 0.20 * (failed / total_pods)

    # Penalize slow convergence
    if len(history) > 6:
        score -= 0.10

    # Penalize pods with scheduling constraints but missing metadata
    # (constraints we can't enforce reduce confidence)
    if total_pods > 0:
        constrained_pods = sum(1 for p in state.pods.values()
                               if p.node_selector or p.tolerations
                               or p.has_pod_anti_affinity or p.topology_spread_constraints)
        pods_without_constraints_data = sum(
            1 for sp in snapshot.pods
            if not sp.is_daemonset and not sp.is_system
            and not sp.node_selector and not sp.tolerations
        )
        # If most pods lack constraint data but cluster likely has constraints,
        # it means agent hasn't collected them yet — reduce confidence slightly
        if constrained_pods == 0 and total_pods > 5:
            score -= 0.05  # likely missing constraint metadata

    return max(0.0, min(1.0, round(score, 2)))


def _empty_result(snapshot: SimulationSnapshot) -> SimulationResult:
    return SimulationResult(
        cycles_run=0,
        converged=False,
        timed_out=False,
        final_state=VirtualClusterState(),
        history=[],
        confidence_score=0.0,
        snapshot_frozen_at=snapshot.frozen_at,
        pod_data_age_seconds=0,
    )


# ─── Stage 6b: Two-Pool Cost Calculation ─────────────────────────────────────

def compute_two_pool_cost(state: VirtualClusterState) -> Dict[str, Any]:
    """Compute costs separately for stateless (spot) and stateful (OD) pools."""
    stateless_nodes = [n for n in state.nodes.values()
                       if n.workload_class == 'stateless' and n.status == 'READY']
    stateful_nodes = [n for n in state.nodes.values()
                      if n.workload_class in ('stateful', 'system') and n.status == 'READY']

    stateless_spot_hourly = sum(n.price_hourly for n in stateless_nodes if n.lifecycle == 'spot')
    stateless_od_hourly = sum(n.price_hourly for n in stateless_nodes if n.lifecycle == 'on-demand')
    stateful_od_hourly = sum(n.price_hourly for n in stateful_nodes)

    return {
        'stateless_node_count': len(stateless_nodes),
        'stateless_spot_count': sum(1 for n in stateless_nodes if n.lifecycle == 'spot'),
        'stateless_hourly_cost': round(stateless_spot_hourly + stateless_od_hourly, 4),
        'stateless_monthly_cost': round((stateless_spot_hourly + stateless_od_hourly) * 730, 2),
        'stateful_node_count': len(stateful_nodes),
        'stateful_hourly_cost': round(stateful_od_hourly, 4),
        'stateful_monthly_cost': round(stateful_od_hourly * 730, 2),
        'total_hourly_cost': round(stateless_spot_hourly + stateless_od_hourly + stateful_od_hourly, 4),
        'total_monthly_cost': round((stateless_spot_hourly + stateless_od_hourly + stateful_od_hourly) * 730, 2),
    }


# ─── Output Builder ──────────────────────────────────────────────────────────

def build_simulation_output(
    result: SimulationResult,
    snapshot: SimulationSnapshot,
    current_node_count: int,
    current_monthly_cost: float,
) -> Dict[str, Any]:
    """Build the enhanced simulation response dict."""
    state = result.final_state
    two_pool = compute_two_pool_cost(state)

    # Build consolidated_nodes from final state
    stateless_by_type: Dict[str, Dict] = {}
    stateful_by_type: Dict[str, Dict] = {}

    for node in state.nodes.values():
        if node.status != 'READY':
            continue
        pods_on = len(state.get_running_pods(node.node_id))
        entry_map = stateless_by_type if node.workload_class == 'stateless' else stateful_by_type
        key = node.instance_type
        if key not in entry_map:
            entry_map[key] = {
                'instance_type': node.instance_type,
                'az': node.az,
                'architecture': node.architecture,
                'vcpu': node.vcpu,
                'memory_gb': node.memory_gb,
                'spot_price': node.price_hourly,
                'od_price': 0,
                'lifecycle': node.lifecycle,
                'workload_class': node.workload_class,
                'risk_probability': 0,
                'ml_score': 0,
                'count': 0,
                'total_pods': 0,
            }
        entry_map[key]['count'] += 1
        entry_map[key]['total_pods'] += pods_on

    # Fill in od_price/risk/ml_score from candidate pools
    for pool in snapshot.candidate_pools:
        for emap in (stateless_by_type, stateful_by_type):
            if pool.instance_type in emap:
                emap[pool.instance_type]['od_price'] = pool.od_price
                emap[pool.instance_type]['risk_probability'] = pool.risk_probability
                emap[pool.instance_type]['ml_score'] = pool.ml_score

    all_nodes = list(stateless_by_type.values()) + list(stateful_by_type.values())
    total_node_count = sum(n['count'] for n in all_nodes)
    total_pods = sum(n['total_pods'] for n in all_nodes)

    sim_spot_count = two_pool['stateless_spot_count'] + sum(
        1 for n in state.nodes.values()
        if n.status == 'READY' and n.workload_class in ('stateful', 'system') and n.lifecycle == 'spot'
    )
    sim_od_count = total_node_count - sim_spot_count
    sim_spot_pct = round((sim_spot_count / total_node_count * 100), 1) if total_node_count > 0 else 0

    # Current stateful cost (unchanged nodes)
    current_stateful_nodes = [n for n in snapshot.nodes
                              if n.workload_class in ('stateful', 'system')]
    current_stateful_monthly = round(sum(n.price_hourly for n in current_stateful_nodes) * 730, 2)

    # Current stateless cost
    current_stateless_nodes = [n for n in snapshot.nodes
                               if n.workload_class == 'stateless']
    current_stateless_monthly = round(sum(n.price_hourly for n in current_stateless_nodes) * 730, 2)

    stateless_savings = round(max(0, current_stateless_monthly - two_pool['stateless_monthly_cost']), 2)
    stateful_savings = round(max(0, current_stateful_monthly - two_pool['stateful_monthly_cost']), 2)

    # Fragmentation pct
    ready_stateless = [n for n in state.nodes.values()
                       if n.status == 'READY' and n.workload_class == 'stateless']
    total_alloc = sum(n.allocatable_cpu_m for n in ready_stateless)
    total_used = sum(n.used_cpu_m for n in ready_stateless)
    frag_pct = round((1 - total_used / total_alloc) * 100, 1) if total_alloc > 0 else 0

    ds_pods = [p for p in snapshot.pods if p.is_daemonset or p.is_system]
    user_pods_count = len(snapshot.pods) - len(ds_pods)

    return {
        # ── Existing fields ──
        'mode': snapshot.karpenter_mode,
        'rightsized': snapshot.use_rightsized,
        'consolidated_nodes': all_nodes,
        'total_node_count': total_node_count,
        'total_pods_packed': total_pods,
        'total_pods_in_cluster': len(snapshot.pods),
        'user_pods': user_pods_count,
        'daemonset_pods': len(ds_pods),
        'daemonset_overhead_cpu_m': snapshot.ds_cpu_overhead + KUBELET_CPU_M,
        'daemonset_overhead_mem_mb': round((snapshot.ds_mem_overhead + KUBELET_MEM_BYTES) / (1024 * 1024)),
        'total_monthly_cost': two_pool['total_monthly_cost'],
        'total_hourly_cost': two_pool['total_hourly_cost'],
        'current_node_count': current_node_count,
        'current_monthly_cost': current_monthly_cost,
        'monthly_savings': round(max(0, current_monthly_cost - two_pool['total_monthly_cost']), 2),
        'nodes_eliminated': max(0, current_node_count - total_node_count),
        'multi_arch': len({n.get('architecture', 'amd64') for n in all_nodes}) > 1,
        'architectures_used': list({n.get('architecture', 'amd64') for n in all_nodes}),

        # ── NEW: Stateless pool ──
        'stateless_node_count': two_pool['stateless_node_count'],
        'stateless_spot_count': two_pool['stateless_spot_count'],
        'stateless_monthly_cost': two_pool['stateless_monthly_cost'],
        'stateless_consolidated_nodes': list(stateless_by_type.values()),
        'stateless_nodes_eliminated': max(0, len(current_stateless_nodes) - two_pool['stateless_node_count']),
        'stateless_monthly_savings': stateless_savings,

        # ── NEW: Stateful pool ──
        'stateful_node_count': two_pool['stateful_node_count'],
        'stateful_monthly_cost': two_pool['stateful_monthly_cost'],
        'stateful_consolidated_nodes': list(stateful_by_type.values()),
        'stateful_monthly_savings': stateful_savings,

        # ── NEW: Combined ──
        'simulated_spot_node_count': sim_spot_count,
        'simulated_od_node_count': sim_od_count,
        'simulated_spot_pct': sim_spot_pct,

        # ── NEW: Convergence ──
        'cycles_to_converge': result.cycles_run,
        'converged': result.converged,
        'timed_out': result.timed_out,
        'pending_pods_peak': state.peak_pending_pods,
        'provisioning_failures': state.total_provisioning_failures,
        'scheduler_fragmentation_pct': frag_pct,

        # ── NEW: Constraint visibility ──
        'pools_skipped_launch_blocked': state.pools_skipped_launch_blocked,
        'pools_skipped_blacklisted': state.pools_skipped_blacklisted,

        # ── NEW: Quality ──
        'confidence_score': result.confidence_score,
        'snapshot_frozen_at': result.snapshot_frozen_at.isoformat(),
        'pod_data_age_seconds': result.pod_data_age_seconds,
        'simulation_engine_version': ENGINE_VERSION,
    }
