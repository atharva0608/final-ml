"""
Distribution Engine — Transforms a PlacementPlan into an ExecutionManifest.
============================================================================
Sits between PodPlacementEngine (produces PlacementPlan) and StatefulExecutor
(drives per-pod state machines).

Pipeline (within a single DE.build() call):
  Layer 0a — Contract validation (plan schema check)
  Layer 0b — InstanceSelectionService.resolve_all() [OPTIONAL — injected by caller]
              Resolves instance_type for all provision entries before grouping.
              If not injected, EE catches FAILED_NO_INSTANCE_TYPE at runtime.
  Layer 1  — ManifestGuard (reject infeasible or noop plans)
  Layer 2  — WorkloadGrouper (aggregate pod steps into workload groups)
  Layer 2b — DependencyGraphBuilder (build DAG from inbound_services + node sharing)
  Layer 2c — WaveBuilder (Kahn's topological sort → execution waves)
  Layer 3  — WorkloadSorter (order workloads by class and risk)
  Layer 4  — MigrationGroupBuilder (assign execution strategy per group)
  Layer 5  — PreconditionSnapshotter (freeze cluster state)

Pure-function module — no Redis/DB writes inside any submodule.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

MANIFEST_TTL_SECONDS = 120
SCHEMA_VERSION = "1.0"

MANIFEST_SCHEMA_REFERENCE = """
manifest (Dict) — produced by DistributionEngine.build():
  manifest_id: str              — "mfst-{sha256_hash[:12]}"
  plan_id: str                  — from PPE feasibility
  schema_version: str
  status: "READY"
  plan_status: str              — "resolved" | "partial" | "draft" | "no_action"
  generated_at: str             — ISO timestamp
  expires_in_seconds: int
  workload_priority_order: List[str]
  migration_groups: List[Dict]  — one per workload, typed by strategy
  parallel_waves: List[Dict]    — wave scheduling metadata (wave_index, workload_class,
                                   group_ids, max_concurrent, barrier_after)
  node_plan: List[Dict]         — from PPE, enriched with instance_type by ISS
  node_layout: Dict             — from PPE BinPacker
  anchor_plan: Dict             — from PPE AnchorPlanner
  cost_projection: Dict         — from PPE CostProjector
  precondition_snapshot: Dict   — frozen cluster state
  budget_consumed: Dict         — {pods, nodes_create, nodes_drain}
  budget_remaining: Dict
  blocked_workloads: List[Dict]
  classification_errors: List[Dict] — DB workloads incorrectly reaching DE (audit)

KEYS THAT DO NOT EXIST in the manifest (common source of bugs):
  provision_nodes  — does not exist, use node_plan[action=provision]
  drain_nodes      — does not exist, use node_plan[action=drain]
  keep_nodes       — does not exist, use node_plan[action=keep]
"""


class UnresolvedInstanceError(Exception):
    """
    GAP 1 — raised when a provision entry still has instance_type=None
    after InstanceSelectionService.resolve_all() has run.
    Caught by the caller (optimize_routes / auto_rebalancer) to abort manifest creation.
    """
    def __init__(self, msg: str, unresolved: Optional[List[str]] = None):
        super().__init__(msg)
        self.unresolved = unresolved or []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Layer 1 — ManifestGuard
# ---------------------------------------------------------------------------

class ManifestGuard:
    """
    Entry gate for the Distribution Engine.
    Uses explicit allowlists — unknown future statuses default to ABORT, not PROCEED.
    """

    PROCEED      = "PROCEED"
    NO_MANIFEST  = "NO_MANIFEST"
    ABORT        = "ABORT"

    NOOP_STATUSES    = frozenset({
        "already_optimal", "no_pods_observed", "stale_data",
        "cluster_not_idle", "no_node_data",
    })
    PROCEED_STATUSES = frozenset({"plan_generated", "partial"})

    @staticmethod
    def check(
        plan: Dict[str, Any],
        wie_profiles: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Returns (decision, reason)."""
        feasibility = plan.get("feasibility") or {}
        status = feasibility.get("status", "")

        if status == "infeasible":
            return ManifestGuard.ABORT, "plan_infeasible"
        if status in ManifestGuard.NOOP_STATUSES:
            return ManifestGuard.NO_MANIFEST, f"placement_was_noop:{status}"
        if status not in ManifestGuard.PROCEED_STATUSES:
            return ManifestGuard.ABORT, f"unknown_plan_status:{status}"
        if not plan.get("movement_plan"):
            return ManifestGuard.NO_MANIFEST, "empty_movement_plan"
        if not wie_profiles:
            return ManifestGuard.ABORT, "no_wie_profiles"
        return ManifestGuard.PROCEED, "all_gates_passed"


# ---------------------------------------------------------------------------
# Layer 2 — WorkloadGrouper
# ---------------------------------------------------------------------------

class WorkloadGrouper:
    """
    Groups movement_plan steps by workload_id.
    Priority: step field (FIX-GAP-9 guaranteed) → WIE profile lookup → derived fallback.
    """

    @staticmethod
    def group(
        movement_plan: List[Dict[str, Any]],
        wie_profiles: Dict[str, Any],
        pods: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, List[Dict]], List[Dict], List[Dict]]:
        """Returns (workload_groups, unmatched_steps, classification_errors).

        classification_errors contains steps whose workload_id maps to a WIE profile
        with workload_class=="db". DB workloads must produce zero movement steps
        (max_spot_replicas=0). Presence here indicates a WIE classification failure
        upstream — not a normal case to handle gracefully.
        """
        pod_to_workload: Dict[str, str] = {}
        for wid, profile in wie_profiles.items():
            for pname in (profile.get("pod_names") or []):
                pod_to_workload[pname] = wid

        workload_groups: Dict[str, List[Dict]] = defaultdict(list)
        unmatched: List[Dict] = []
        classification_errors: List[Dict] = []

        for step in movement_plan:
            pod_name = step.get("pod_name", "")
            wid = (
                step.get("workload_id")
                or pod_to_workload.get(pod_name)
                or WorkloadGrouper._derive_id(step.get("namespace", ""), pod_name)
            )
            if not wid:
                unmatched.append(step)
                continue

            # System/DB rejection gate: DaemonSets, system workloads, and DB workloads
            # must never appear in movement_plan. Any step here indicates WIE upstream failure.
            profile = wie_profiles.get(wid, {})
            wclass = WorkloadSorter._derive_class(profile)
            if wclass in ("db", "system"):
                logger.warning(
                    "[WorkloadGrouper] %s workload %s appeared in movement_plan — "
                    "indicates WIE classification failure upstream. pod=%s",
                    wclass.upper(), wid, pod_name,
                )
                classification_errors.append({
                    "workload_id": wid,
                    "pod_name":    pod_name,
                    "error":       f"{wclass}_workload_in_movement_plan",
                    "severity":    "WARNING",
                })
                continue

            workload_groups[wid].append(step)

        return dict(workload_groups), unmatched, classification_errors

    @staticmethod
    def _derive_id(namespace: str, pod_name: str) -> str:
        parts = pod_name.rsplit("-", 2)
        prefix = parts[0] if len(parts) >= 2 else pod_name
        return f"{namespace}/{prefix}" if namespace else prefix


# ---------------------------------------------------------------------------
# Layer 3 — WorkloadSorter
# ---------------------------------------------------------------------------

class WorkloadSorter:
    """
    Orders workloads: stateless first (fastest, lowest risk), then stateful, then db.
    Within each class: highest-risk / highest-criticality processed first.
    DB workloads must never appear here — presence indicates WIE classification failure upstream.
    """

    TIER_SCORE = {"Platinum": 4, "Gold": 3, "Silver": 2, "Bronze": 1}
    # Safety net order — if DB workload incorrectly reaches this layer, process it first under
    # maximum scrutiny. Normal path: DB workloads produce zero movement steps.
    CLASS_ORDER = {"db": 0, "stateful": 1, "mixed": 2, "stateless": 3}

    @staticmethod
    def _derive_class(profile: Dict[str, Any]) -> str:
        """Derive workload_class from WIE profile fields when explicit field absent."""
        wclass = profile.get("workload_class") or ""
        if wclass in ("db", "stateful", "stateless", "mixed", "system", "anchor"):
            return wclass
        # Fallback derivation
        # DaemonSet → system (authoritative controller_kind check)
        ctrl_kind = profile.get("controller_kind") or ""
        if ctrl_kind == "DaemonSet":
            return "system"
        role = (profile.get("role") or "").upper()
        if role in ("SYSTEM", "CONTROL_PLANE"):
            return "system"
        app_type = (profile.get("classifier_app_type") or profile.get("detected_app_type") or "").lower()
        _DB = frozenset({"redis", "postgres", "postgresql", "mysql", "mariadb",
                         "mongodb", "mongo", "elasticsearch", "kafka", "zookeeper",
                         "cassandra", "etcd", "memcached"})
        if any(m in app_type for m in _DB) or profile.get("has_pvc"):
            return "db"
        if profile.get("data_safety") == "STATEFUL":
            return "stateful"
        if ctrl_kind in ("Deployment", "ReplicaSet"):
            return "stateless"
        return "mixed"

    @staticmethod
    def sort(
        workload_groups: Dict[str, List[Dict]],
        wie_profiles: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> List[str]:
        drain_node_names = {
            e["node_name"] for e in (plan.get("node_plan") or [])
            if e.get("action") == "drain" and e.get("node_name")
        }

        def priority(wid: str) -> int:
            profile = wie_profiles.get(wid, {})
            steps = workload_groups[wid]
            criticality = WorkloadSorter.TIER_SCORE.get(profile.get("tier", "Bronze"), 1)
            safety_risk = sum(
                1 for s in steps
                if s.get("from_capacity_type") != s.get("to_capacity_type")
            )
            urgency = 2 if (
                profile.get("data_safety") == "STATEFUL"
                and any(s.get("from_capacity_type") == "spot" for s in steps)
            ) else 1
            pods_from_drainable = sum(
                1 for s in steps
                if s.get("from_node") in drain_node_names
            )
            return (criticality * safety_risk) + (pods_from_drainable * urgency)

        return sorted(
            workload_groups.keys(),
            key=lambda w: (
                # Primary: hard class order (db=0, stateful=1, mixed=2, stateless=3)
                WorkloadSorter.CLASS_ORDER.get(
                    WorkloadSorter._derive_class(wie_profiles.get(w, {})), 4
                ),
                # Secondary: risk priority within same class (higher = processed first)
                -priority(w),
                w,
            ),
        )


# ---------------------------------------------------------------------------
# Layer 2b — DependencyGraphBuilder
# ---------------------------------------------------------------------------

class DependencyGraphBuilder:
    """
    Builds a DAG of workload dependencies from WIE profiles and node_plan.
    Used by WaveBuilder to determine which workloads can execute in parallel.
    """

    @staticmethod
    def build(
        workload_groups: Dict[str, List[Dict]],
        wie_profiles: Dict[str, Any],
        node_plan: List[Dict[str, Any]],
    ) -> Dict[str, Set[str]]:
        """
        Returns {workload_id: set_of_workload_ids_that_must_complete_first}.

        Dependency sources:
        1. inbound_services: if A's inbound_services contains B, then A calls B,
           so B must be stable before A migrates → deps[A].add(B)
        2. Shared provision node: workloads targeting the same provision node
           are serialized to avoid node capacity race
        """
        migration_ids = set(workload_groups.keys())
        deps: Dict[str, Set[str]] = {wid: set() for wid in migration_ids}

        # Rule 1: inbound_services dependency edges
        for wid, profile in wie_profiles.items():
            if wid not in migration_ids:
                continue
            callers = profile.get("inbound_services") or []
            for caller_wid in callers:
                if caller_wid in migration_ids and caller_wid != wid:
                    deps[caller_wid].add(wid)

        # Rule 2: shared provision node serialization
        prov_node_to_wids: Dict[str, List[str]] = defaultdict(list)
        for wid, steps in workload_groups.items():
            seen_nodes: Set[str] = set()
            for step in steps:
                to_node = step.get("to_node", "")
                if to_node and to_node.startswith("provision-") and to_node not in seen_nodes:
                    prov_node_to_wids[to_node].append(wid)
                    seen_nodes.add(to_node)
                    break

        for _node, wids in prov_node_to_wids.items():
            for i in range(1, len(wids)):
                if wids[i] != wids[i - 1]:
                    deps[wids[i]].add(wids[i - 1])

        return deps


# ---------------------------------------------------------------------------
# Layer 2c — WaveBuilder
# ---------------------------------------------------------------------------

class WaveBuilder:
    """
    Produces parallel_waves metadata using Kahn's topological sort.
    Respects the hard class barrier: db → stateful → stateless.
    Within each class, independent workloads execute in parallel waves.
    """

    MAX_CONCURRENT: Dict[str, int] = {
        "db":        1,
        "stateful":  3,
        "stateless": 5,
        "mixed":     8,
        "batch":     8,
    }

    @staticmethod
    def build(
        ordered: List[str],
        dep_graph: Dict[str, Set[str]],
        wie_profiles: Dict[str, Any],
        migration_groups: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Returns parallel_waves: List[Dict] — scheduling metadata for ExecutionEngine.
        Each wave: wave_index, workload_class, group_ids, max_concurrent, barrier_after.
        """
        if not ordered:
            return []

        wid_to_gid: Dict[str, str] = {
            g.get("workload_id"): g.get("group_id")
            for g in migration_groups
            if g.get("workload_id") and g.get("group_id")
        }

        class_buckets: Dict[str, List[str]] = defaultdict(list)
        for wid in ordered:
            wclass = WorkloadSorter._derive_class(wie_profiles.get(wid, {}))
            class_buckets[wclass].append(wid)

        waves: List[Dict[str, Any]] = []
        wave_index = 0

        for wclass in ("db", "stateful", "mixed", "stateless"):
            wids_in_class = class_buckets.get(wclass, [])
            if not wids_in_class:
                continue

            scoped_deps: Dict[str, Set[str]] = {
                wid: dep_graph.get(wid, set()) & set(wids_in_class)
                for wid in wids_in_class
            }
            in_degree = {wid: len(d) for wid, d in scoped_deps.items()}
            class_waves = WaveBuilder._kahn_waves(wids_in_class, scoped_deps, in_degree)

            max_conc = WaveBuilder.MAX_CONCURRENT.get(wclass, 5)
            for wave_num, wave_wids in enumerate(class_waves):
                group_ids = [wid_to_gid[w] for w in wave_wids if w in wid_to_gid]
                if not group_ids:
                    continue
                waves.append({
                    "wave_index":     wave_index,
                    "workload_class": wclass,
                    "group_ids":      group_ids,
                    "max_concurrent": min(max_conc, len(group_ids)),
                    "barrier_after":  True,
                })
                wave_index += 1

        return waves

    @staticmethod
    def _kahn_waves(
        wids: List[str],
        deps: Dict[str, Set[str]],
        in_degree: Dict[str, int],
    ) -> List[List[str]]:
        """Kahn's algorithm returning list-of-waves (not a flat topological order)."""
        waves: List[List[str]] = []
        remaining = set(wids)

        while remaining:
            current_wave = [w for w in remaining if in_degree.get(w, 0) == 0]
            if not current_wave:
                logger.warning(
                    "[WaveBuilder] Dependency cycle detected among %d workloads — "
                    "forcing remaining into single wave", len(remaining)
                )
                waves.append(list(remaining))
                break

            waves.append(current_wave)
            remaining -= set(current_wave)

            for completed in current_wave:
                for w in remaining:
                    if completed in deps.get(w, set()):
                        in_degree[w] = max(0, in_degree.get(w, 0) - 1)

        return waves


# ---------------------------------------------------------------------------
# Layer 4 — MigrationGroupBuilder
# ---------------------------------------------------------------------------

class MigrationGroupBuilder:
    """
    Builds a typed migration group (BLUE_GREEN or BATCH) for each workload.
    Node enforcement spec is embedded here — Execution Engine applies it blindly.
    Reads node resource state from plan['node_layout'] (post-BinPacker, accurate).
    """

    @staticmethod
    def group_type(profile: Dict[str, Any]) -> str:
        """Map workload to execution strategy.
        DB → SERIAL (one pod at a time, readiness gated, class barrier).
        Stateful / Platinum / Gold / disruption-unsafe → BLUE_GREEN.
        Stateless → ROLLING (PDB-respecting batches).
        """
        wclass = WorkloadSorter._derive_class(profile)
        if wclass == "db":
            return "SERIAL"
        if (
            wclass == "stateful"
            or profile.get("data_safety") == "STATEFUL"
            or profile.get("is_critical") is True
            or profile.get("tier") in ("Platinum", "Gold")
            or profile.get("disruption_safe") is False
        ):
            return "BLUE_GREEN"
        if wclass == "stateless":
            return "ROLLING"
        return "BATCH"

    @staticmethod
    def build_node_enforcement(to_node: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reads node state from plan['node_layout'] (post-assignment resource state).
        Embeds fallback affinity strategy for nodes not yet registered (provisioned nodes).
        ip_available is None until NodeMetadata pipeline gap is resolved.
        """
        node_data: Dict[str, Any] = {}
        layout = plan.get("node_layout") or {}

        for az_data in layout.get("by_az", {}).values():
            for n in az_data.get("nodes", []):
                if n.get("node_name") == to_node:
                    node_data = n
                    break
            if node_data:
                break

        if not node_data:
            for n in layout.get("provision_required", []):
                if n.get("node_name") == to_node:
                    node_data = n
                    break

        resources = node_data.get("resources", {})

        return {
            "strategy":   "nodeName",
            "spec_patch": {"nodeName": to_node},
            "fallback_strategy": "nodeAffinity",
            "fallback_spec_patch": {
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [{
                                "matchExpressions": [{
                                    "key":      "kubernetes.io/hostname",
                                    "operator": "In",
                                    "values":   [to_node],
                                }]
                            }]
                        }
                    }
                }
            },
            "node_resources_at_plan_time": {
                "allocatable_cpu_millicores": resources.get("allocatable_cpu_millicores"),
                "allocatable_memory_bytes":   resources.get("allocatable_memory_bytes"),
                "cpu_remaining_millicores":   resources.get("cpu_remaining_millicores"),
                "memory_remaining_bytes":     resources.get("memory_remaining_bytes"),
                "cpu_utilization_after_pct":  resources.get("cpu_utilization_after_pct"),
                "ip_available":               None,
                "capacity_type":              node_data.get("capacity_type"),
                "az":                         node_data.get("az"),
                "state":                      node_data.get("state"),
            },
        }

    @staticmethod
    def build_serial(
        workload_id: str,
        profile: Dict[str, Any],
        steps: List[Dict[str, Any]],
        plan: Dict[str, Any],
        budget: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        SERIAL executor: one pod at a time. Only proceed to pod N+1 after pod N is Running
        and its readiness probe passes. Halt entire group on any timeout failure.
        """
        mechanism = MigrationGroupBuilder._detect_mechanism(profile)
        _provision_nodes: set = {
            n.get("node_name") for n in (
                (plan.get("node_layout") or {}).get("provision_required") or []
            )
        }
        allowed = steps[:budget["pods"]]
        deferred = [s.get("pod_name", "") for s in steps[budget["pods"]:] ]
        budget["pods"] -= len(allowed)

        serial_steps: List[Dict] = [
            {
                "pod_name":    s.get("pod_name"),
                "namespace":   s.get("namespace"),
                "workload_id": s.get("workload_id"),
                "from_node":   s.get("from_node"),
                "to_node":     s.get("to_node"),
                "to_az":       s.get("to_az"),
                "movement_cost": s.get("movement_cost"),
                "node_enforcement": MigrationGroupBuilder.build_node_enforcement(
                    s.get("to_node", ""), plan
                ),
                "requires_node_provision": s.get("to_node") in _provision_nodes,
                "resource_requirements": {
                    "cpu_request_millicores": s.get("cpu_request_millicores"),
                    "memory_request_bytes":   s.get("memory_request_bytes"),
                },
                "state_machine": {
                    "initial_state": "PENDING",
                    "states": [
                        "PENDING", "PROVISIONING_NEW", "WAITING_READY",
                        "OBSERVING", "DELETING_OLD", "DONE",
                    ],
                    "timeouts_seconds": {
                        "PROVISIONING_NEW": 120,
                        "WAITING_READY":    300,
                        "OBSERVING":        60,
                        "DELETING_OLD":     60,
                    },
                    # SERIAL: halt group on WAITING_READY timeout, trigger rollback
                    "on_timeout": "HALT_GROUP_AND_ROLLBACK",
                    "rollback": MigrationGroupBuilder._build_rollback(mechanism),
                },
            }
            for s in allowed
        ]

        return {
            "group_id":                f"serial-{workload_id}",
            "workload_id":             workload_id,
            "type":                    "SERIAL",
            "execution":               "SEQUENTIAL_GATED",
            "traffic_shift_mechanism": mechanism,
            "readiness_timeout_seconds": 300,
            "halt_class_on_failure":   True,
            "steps":                   serial_steps,
            "deferred_pods":           deferred,
            "pod_count":               len(serial_steps),
        }

    @staticmethod
    def build_rolling(
        workload_id: str,
        profile: Dict[str, Any],
        steps: List[Dict[str, Any]],
        plan: Dict[str, Any],
        budget: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        ROLLING executor: PDB-aware batches for stateless workloads.
        Batch size = min(max_batch_size, floor(total_pods * 0.25)).
        Never evict if doing so would breach PDB minAvailable.
        """
        _provision_nodes: set = {
            n.get("node_name") for n in (
                (plan.get("node_layout") or {}).get("provision_required") or []
            )
        }
        allowed  = steps[:budget["pods"]]
        deferred = [s.get("pod_name", "") for s in steps[budget["pods"]:] ]
        budget["pods"] -= len(allowed)

        pdb_min = profile.get("pdb_min_available")
        pdb_max_unavail = profile.get("pdb_max_unavailable")
        ready_replicas = profile.get("ready_replicas") or len(allowed)

        # PDB-safe batch size: never take down more than maxUnavailable at once
        if pdb_max_unavail is not None and pdb_max_unavail > 0:
            batch_size = min(pdb_max_unavail, max(1, math.ceil(len(allowed) * 0.25)))
        else:
            batch_size = max(1, math.ceil(len(allowed) * 0.25))

        batches: List[Dict] = []
        for i in range(0, len(allowed), batch_size):
            batch_steps = allowed[i:i + batch_size]
            batches.append({
                "batch_index": i // batch_size + 1,
                "steps": [
                    {
                        "pod_name":    s.get("pod_name"),
                        "namespace":   s.get("namespace"),
                        "workload_id": s.get("workload_id"),
                        "from_node":   s.get("from_node"),
                        "to_node":     s.get("to_node"),
                        "to_az":       s.get("to_az"),
                        "movement_cost": s.get("movement_cost"),
                        "node_enforcement": MigrationGroupBuilder.build_node_enforcement(
                            s.get("to_node", ""), plan
                        ),
                        "requires_node_provision": s.get("to_node") in _provision_nodes,
                        "resource_requirements": {
                            "cpu_request_millicores": s.get("cpu_request_millicores"),
                            "memory_request_bytes":   s.get("memory_request_bytes"),
                        },
                    }
                    for s in batch_steps
                ],
                "pdb_check": {
                    "min_available":      pdb_min,
                    "max_unavailable":    pdb_max_unavail,
                    "ready_replicas":     ready_replicas,
                    "batch_evict_count":  len(batch_steps),
                    "safe_to_proceed":    (
                        pdb_min is None
                        or (ready_replicas - len(batch_steps)) >= pdb_min
                    ),
                },
                "readiness_timeout_seconds": 120,
                "proceed_on_partial_ready":  False,
            })

        return {
            "group_id":      f"rolling-{workload_id}",
            "workload_id":   workload_id,
            "type":          "ROLLING",
            "execution":     "PARALLEL_BATCHED_PDB_SAFE",
            "batch_size":    batch_size,
            "batches":       batches,
            "deferred_pods": deferred,
            "pod_count":     len(allowed),
            "pdb_constraints": {
                "min_available":   pdb_min,
                "max_unavailable": pdb_max_unavail,
                "ready_replicas":  ready_replicas,
            },
            "rollback": {
                "on_batch_failure": "STOP_NEXT_BATCHES",
                "on_pod_failure":   "SKIP_POD_ALERT",
            },
        }

    @staticmethod
    def build_blue_green(
        workload_id: str,
        profile: Dict[str, Any],
        steps: List[Dict[str, Any]],
        plan: Dict[str, Any],
        budget: Dict[str, int],
    ) -> Dict[str, Any]:
        mechanism = MigrationGroupBuilder._detect_mechanism(profile)
        # GAP 5: StatefulSets must move in reverse ordinal order (pod-2 → pod-1 → pod-0)
        if profile.get("controller_kind") == "StatefulSet":
            steps = sorted(steps, key=MigrationGroupBuilder._pod_ordinal, reverse=True)
        # GAP 6: steps targeting not-yet-existing nodes need provision sequencing
        _provision_nodes: set = {
            n.get("node_name") for n in (
                (plan.get("node_layout") or {}).get("provision_required") or []
            )
        }
        group_steps: List[Dict] = []
        deferred: List[str] = []

        for step in steps:
            if budget["pods"] <= 0:
                deferred.append(step.get("pod_name", ""))
                continue
            group_steps.append({
                "pod_name":   step.get("pod_name"),
                "namespace":  step.get("namespace"),
                "workload_id": step.get("workload_id"),
                "from_node":  step.get("from_node"),
                "from_az":    step.get("from_az"),
                "to_node":    step.get("to_node"),
                "to_az":      step.get("to_az"),
                "movement_cost": step.get("movement_cost"),
                "node_enforcement": MigrationGroupBuilder.build_node_enforcement(
                    step.get("to_node", ""), plan
                ),
                "requires_node_provision": step.get("to_node") in _provision_nodes,
                "resource_requirements": {
                    "cpu_request_millicores": step.get("cpu_request_millicores"),
                    "memory_request_bytes":   step.get("memory_request_bytes"),
                },
                "state_machine": {
                    "initial_state": "PENDING",
                    "states": [
                        "PENDING", "PROVISIONING_NEW", "WAITING_READY",
                        "SHIFTING_TRAFFIC", "OBSERVING", "DELETING_OLD", "DONE",
                    ],
                    "timeouts_seconds": {
                        "PROVISIONING_NEW": 120,
                        "WAITING_READY":    180,
                        "SHIFTING_TRAFFIC": 30,
                        "OBSERVING":        60,
                        "DELETING_OLD":     60,
                    },
                    "rollback": MigrationGroupBuilder._build_rollback(mechanism),
                },
            })
            budget["pods"] -= 1

        return {
            "group_id":                f"bg-{workload_id}",
            "workload_id":             workload_id,
            "type":                    "BLUE_GREEN",
            "execution":               "SEQUENTIAL",
            "traffic_shift_mechanism": mechanism,
            "stability_window_seconds": 60,
            "steps":                   group_steps,
            "deferred_pods":           deferred,
            "pod_count":               len(group_steps),
        }

    @staticmethod
    def build_batch(
        workload_id: str,
        profile: Dict[str, Any],
        steps: List[Dict[str, Any]],
        plan: Dict[str, Any],
        budget: Dict[str, int],
    ) -> Dict[str, Any]:
        # GAP 5: StatefulSets must move in reverse ordinal order
        if profile.get("controller_kind") == "StatefulSet":
            steps = sorted(steps, key=MigrationGroupBuilder._pod_ordinal, reverse=True)
        # GAP 6: steps targeting not-yet-existing nodes need provision sequencing
        _provision_nodes: set = {
            n.get("node_name") for n in (
                (plan.get("node_layout") or {}).get("provision_required") or []
            )
        }
        allowed  = steps[:budget["pods"]]
        deferred = [s.get("pod_name", "") for s in steps[budget["pods"]:]]
        budget["pods"] -= len(allowed)

        batch_size = max(1, math.ceil(len(allowed) * 0.25))
        batches: List[Dict] = []
        for i in range(0, len(allowed), batch_size):
            batch_steps = allowed[i:i + batch_size]
            batches.append({
                "batch_index": i // batch_size + 1,
                "steps": [
                    {
                        "pod_name":    s.get("pod_name"),
                        "namespace":   s.get("namespace"),
                        "workload_id": s.get("workload_id"),
                        "from_node":   s.get("from_node"),
                        "to_node":     s.get("to_node"),
                        "to_az":       s.get("to_az"),
                        "movement_cost": s.get("movement_cost"),
                        "node_enforcement": MigrationGroupBuilder.build_node_enforcement(
                            s.get("to_node", ""), plan
                        ),
                        "requires_node_provision": s.get("to_node") in _provision_nodes,
                        "resource_requirements": {
                            "cpu_request_millicores": s.get("cpu_request_millicores"),
                            "memory_request_bytes":   s.get("memory_request_bytes"),
                        },
                    }
                    for s in batch_steps
                ],
                "readiness_timeout_seconds": 60,
                "proceed_on_partial_ready":  False,
            })

        return {
            "group_id":      f"batch-{workload_id}",
            "workload_id":   workload_id,
            "type":          "BATCH",
            "execution":     "PARALLEL_BATCHED",
            "batch_size":    batch_size,
            "batches":       batches,
            "deferred_pods": deferred,
            "pod_count":     len(allowed),
            "pdb_constraints": {
                "min_available":   profile.get("pdb_min_available"),
                "max_unavailable": profile.get("pdb_max_unavailable"),
                "ready_replicas":  profile.get("ready_replicas"),
            },
            "rollback": {
                "on_batch_failure": "STOP_NEXT_BATCHES",
                "on_pod_failure":   "SKIP_POD_ALERT",
            },
        }

    @staticmethod
    def _detect_mechanism(profile: Dict[str, Any]) -> str:
        app_type = (profile.get("app_type") or profile.get("detected_app_type") or "").lower()
        if app_type == "redis":
            return "sentinel_promotion"
        if app_type in ("postgresql", "mysql", "mariadb"):
            return "connection_pool_reroute"
        if app_type in ("kafka", "zookeeper", "elasticsearch", "cassandra"):
            return "cluster_rebalance"
        return "service_selector_patch"

    @staticmethod
    def _build_rollback(mechanism: str) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "PROVISIONING_NEW": {
                "action":     "delete_new_pod",
                "on_failure": "ABORT",
            },
            "WAITING_READY": {
                "action":     "retry_3x_then_abort",
                "on_failure": "ABORT",
            },
            "DELETING_OLD": {
                "action":     "skip_delete_emit_alert",
                "on_failure": "ALERT_ONLY",
            },
        }
        traffic_stages: Dict[str, Any] = {
            "sentinel_promotion": {
                "SHIFTING_TRAFFIC": {
                    "action":     "demote_new_failback_to_old",
                    "revert_api": "sentinel_failback",
                    "on_failure": "ABORT",
                },
                "OBSERVING": {
                    "action":     "demote_new_failback_to_old",
                    "revert_api": "sentinel_failback",
                    "on_failure": "ABORT",
                },
            },
            "connection_pool_reroute": {
                "SHIFTING_TRAFFIC": {
                    "action":     "reroute_pool_back_to_old",
                    "revert_api": "update_pool_target",
                    "on_failure": "ABORT",
                },
                "OBSERVING": {
                    "action":     "reroute_pool_back_to_old",
                    "revert_api": "update_pool_target",
                    "on_failure": "ABORT",
                },
            },
            "service_selector_patch": {
                "SHIFTING_TRAFFIC": {
                    "action":     "patch_selector_back_to_old_label",
                    "revert_api": "kubectl_patch_service",
                    "on_failure": "ABORT",
                },
                "OBSERVING": {
                    "action":     "patch_selector_back_to_old_label",
                    "revert_api": "kubectl_patch_service",
                    "on_failure": "ABORT",
                },
            },
            "cluster_rebalance": {
                "SHIFTING_TRAFFIC": {
                    "action":     "trigger_rebalance_back",
                    "revert_api": "cluster_api_rebalance",
                    "on_failure": "ALERT_ONLY",
                },
                "OBSERVING": {
                    "action":     "trigger_rebalance_back",
                    "revert_api": "cluster_api_rebalance",
                    "on_failure": "ALERT_ONLY",
                },
            },
        }
        return {**base, **traffic_stages.get(mechanism, {})}

    @staticmethod
    def _pod_ordinal(step: Dict[str, Any]) -> int:
        """Extract trailing ordinal integer from pod name for StatefulSet ordering."""
        name = step.get("pod_name") or ""
        parts = name.rsplit("-", 1)
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0


# ---------------------------------------------------------------------------
# Layer 5 — PreconditionSnapshotter
# ---------------------------------------------------------------------------

class PreconditionSnapshotter:
    """
    Freezes the cluster state (only plan-relevant nodes/pods) that must still
    be true when the Execution Engine starts. RaceGuard compares against this.
    Keeping the snapshot minimal (relevant nodes/pods only) makes comparison fast.
    """

    @staticmethod
    def snapshot(
        plan: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        pods: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        relevant_nodes: set = set(
            plan.get("anchor_plan", {}).get("anchor_nodes") or []
        )
        relevant_pods: set = set()

        for step in plan.get("movement_plan") or []:
            if step.get("from_node"):
                relevant_nodes.add(step["from_node"])
            if step.get("to_node"):
                relevant_nodes.add(step["to_node"])
            if step.get("pod_name"):
                relevant_pods.add(step["pod_name"])

        for entry in plan.get("node_plan") or []:
            if entry.get("node_name"):
                relevant_nodes.add(entry["node_name"])

        node_map = {n["node_name"]: n for n in nodes if n.get("node_name")}
        pod_map  = {p["pod_name"]:  p for p in pods  if p.get("pod_name")}

        now = _now_utc()

        return {
            "snapshot_timestamp":   now,
            "snapshot_valid_until": MANIFEST_TTL_SECONDS,
            "nodes": {
                name: {
                    "status":        node_map[name].get("status"),
                    "capacity_type": node_map[name].get("capacity_type"),
                    "az":            node_map[name].get("az"),
                    "pod_count":     node_map[name].get("pod_count"),
                }
                for name in relevant_nodes
                if name in node_map
            },
            "pods": {
                name: {
                    "node":   pod_map[name].get("node_name"),
                    "status": pod_map[name].get("status"),
                    "az":     pod_map[name].get("az"),
                }
                for name in relevant_pods
                if name in pod_map
            },
            "az_capacity": {
                az: {
                    "node_count":  sum(1 for n in nodes if n.get("az") == az),
                    "ready_count": sum(
                        1 for n in nodes
                        if n.get("az") == az and n.get("status") == "Ready"
                    ),
                }
                for az in {n["az"] for n in nodes if n.get("az")}
            },
        }


# ---------------------------------------------------------------------------
# Orchestrator — DistributionEngine
# ---------------------------------------------------------------------------

class DistributionEngine:
    """
    Main entry point.

    `plan`         — PlacementPlan as dict (from PodPlacementEngine.to_dict())
    `wie_profiles` — workload_id → WIE profile dict
    `nodes`        — current node list (for PreconditionSnapshotter)
    `pods`         — current pod list  (for PreconditionSnapshotter + WorkloadGrouper)
    """

    @staticmethod
    def _enrich_profiles(
        wie_profiles: Dict[str, Any],
        movement_steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Inject fields WIE doesn't emit directly but DE needs. Returns a shallow copy.

        GAP 2 — pod_names: WIE classifies controllers, not individual pods.
                Derived from movement steps which already carry workload_id (FIX-GAP-9).
                Enables WorkloadGrouper priority-2 lookup as secondary validation.
        GAP 3 — is_critical: WIE emits tier/criticality_score; group_type() needs a bool.
                Derived as: tier in (Platinum, Gold) OR data_safety == STATEFUL.
        """
        enriched = {wid: dict(p) for wid, p in wie_profiles.items()}
        for step in movement_steps:
            wid = step.get("workload_id")
            if wid and wid in enriched:
                enriched[wid].setdefault("pod_names", []).append(step.get("pod_name", ""))
        for profile in enriched.values():
            if "is_critical" not in profile:
                tier = profile.get("tier", "")
                profile["is_critical"] = (
                    tier in ("Platinum", "Gold")
                    or profile.get("data_safety") == "STATEFUL"
                )
        return enriched

    @staticmethod
    def _validate_resolved_instances(node_plan: List[Dict], iss_was_run: bool) -> None:
        """
        GAP 1 — enforces instance_type resolution.
        - When ISS ran: ANY provision entry with instance_type=None is fatal → raises UnresolvedInstanceError.
        - When ISS skipped (no ISS injected): logs WARNING only — EE will catch FAILED_NO_INSTANCE_TYPE.
        """
        unresolved = [
            e.get("node_name", "?") for e in node_plan
            if e.get("action") == "provision" and not e.get("instance_type")
        ]
        if not unresolved:
            return
        if iss_was_run:
            raise UnresolvedInstanceError(
                f"DistributionEngine: {len(unresolved)} provision entr"
                f"{'y' if len(unresolved) == 1 else 'ies'} still have instance_type=None "
                f"after ISS.resolve_all() — nodes: {unresolved}. "
                f"Aborting manifest creation.",
                unresolved=unresolved,
            )
        logger.warning(
            "DistributionEngine: %d provision entries have instance_type=None — "
            "ISS was not injected; EE will catch FAILED_NO_INSTANCE_TYPE. "
            "nodes: %s",
            len(unresolved), unresolved,
        )

    @staticmethod
    def _contract_guard(plan: Dict[str, Any]) -> Optional[str]:
        """
        Medium C — PPE → DE contract validation.
        Stronger than ManifestGuard: checks internal field shapes, not just status.
        Returns an error string or None.
        """
        feas = plan.get("feasibility") or {}

        # Required top-level keys
        for key in ("movement_plan", "feasibility"):
            if key not in plan:
                return f"contract_violation:missing_top_key:{key}"

        # movement_plan entries must have pod_name + to_node (or blocked_by)
        for i, step in enumerate(plan.get("movement_plan") or []):
            if not step.get("pod_name"):
                return f"contract_violation:movement_step[{i}]:missing_pod_name"
            if not step.get("to_node") and not step.get("blocked_by"):
                return f"contract_violation:movement_step[{i}]:to_node_and_blocked_by_both_null"

        # node_plan provision entries must have az + capacity_type + packed_pods
        for j, entry in enumerate(plan.get("node_plan") or []):
            if entry.get("action") != "provision":
                continue
            if not entry.get("az"):
                return f"contract_violation:node_plan[{j}]:provision_missing_az"
            if not entry.get("capacity_type"):
                return f"contract_violation:node_plan[{j}]:provision_missing_capacity_type"
            if not entry.get("packed_pods"):
                return f"contract_violation:node_plan[{j}]:provision_missing_packed_pods"

        # cluster_id must be set (PPE injects it; missing = PPE didn't set it)
        if not feas.get("cluster_id"):
            return "contract_violation:feasibility.cluster_id_missing"

        return None

    # ── Layer 5 helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _tag_logical_roles(node_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Annotate each node_plan entry with a logical_role string.
        Rules:
          stateful + OD        → od_anchor
          stateless + Spot     → spot_stateless
          mixed/batch + Spot   → spot_worker
          keep node + OD       → od_anchor
          keep node + Spot     → spot_stateless
        """
        tagged = []
        for entry in node_plan:
            e = dict(entry)
            action = (e.get("action") or "").lower()
            wc     = (e.get("workload_class") or "").lower()
            ct     = (e.get("capacity_type")  or "").lower()
            is_od  = ct in ("on-demand", "on_demand", "ondemand") or (not ct and action == "keep")
            is_spot = "spot" in ct

            if action == "keep":
                e["logical_role"] = "od_anchor" if is_od else ("spot_stateless" if is_spot else "od_anchor")
            elif action == "provision":
                if wc == "stateful" or is_od:
                    e["logical_role"] = "od_anchor"
                elif wc in ("mixed", "batch"):
                    e["logical_role"] = "spot_worker"
                else:
                    e["logical_role"] = "spot_stateless"
            elif action == "drain":
                e["logical_role"] = None
            else:
                e["logical_role"] = None
            tagged.append(e)
        return tagged

    @staticmethod
    def build(
        plan: Dict[str, Any],
        wie_profiles: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        pods: List[Dict[str, Any]],
        instance_selection_service=None,  # Problems 7, 8: optional ISS injection
        db=None,                          # required if ISS provided
    ) -> Dict[str, Any]:

        # ── Layer 0a — PPEContractGuard (Medium C) ───────────────────────────
        contract_err = DistributionEngine._contract_guard(plan)
        if contract_err:
            logger.error("DistributionEngine: contract_guard failed — %s", contract_err)
            return {
                "manifest_id":      None,
                "status":           "ABORT",
                "reason":           contract_err,
                "migration_groups": [],
                "schema_version":   SCHEMA_VERSION,
            }

        # ── Layer 0b — InstanceSelectionService (Problems 7, 8) ───────────────
        # Resolves instance_type for every provision entry in node_plan
        # BEFORE ManifestGuard and BEFORE build_node_enforcement() (Layer 4).
        cluster_id = plan.get("feasibility", {}).get("cluster_id")
        iss_was_run = False
        if instance_selection_service is not None and cluster_id:
            try:
                raw_node_plan = plan.get("node_plan") or []
                resolved_plan = instance_selection_service.resolve_all(
                    cluster_id=cluster_id,
                    node_plan=raw_node_plan,
                    diversify=True,
                )
                plan = dict(plan)
                plan["node_plan"] = resolved_plan
                iss_was_run = True
                logger.info(
                    "DistributionEngine: ISS resolved %d provision entries for cluster=%s",
                    len([e for e in resolved_plan if e.get("action") == "provision"]),
                    cluster_id,
                )
            except Exception as _iss_err:
                logger.warning(
                    "DistributionEngine: ISS.resolve_all() failed (non-fatal) "
                    "cluster=%s error=%s — proceeding without instance type resolution",
                    cluster_id, _iss_err,
                )

        # GAP 1 — enforce instance_type resolution
        DistributionEngine._validate_resolved_instances(
            plan.get("node_plan") or [], iss_was_run=iss_was_run
        )

        # Layer 1 — ManifestGuard
        decision, reason = ManifestGuard.check(plan, wie_profiles)
        if decision != ManifestGuard.PROCEED:
            logger.info("DistributionEngine: gate=%s reason=%s", decision, reason)
            return {
                "manifest_id":      None,
                "status":           decision,
                "reason":           reason,
                "migration_groups": [],
                "schema_version":   SCHEMA_VERSION,
            }

        # Layer 2 — WorkloadGrouper
        # Only pass actionable steps: skip pods blocked by no_capacity (to_node=None).
        # no_capacity pods remain in the PlacementPlan movement_plan for audit purposes
        # but the Distribution Engine must not try to enforce a move with no target node.
        actionable_movement = [
            s for s in plan["movement_plan"]
            if s.get("to_node") and not s.get("blocked_by")
        ]
        # Enrich profiles with derived fields WIE doesn't emit directly (GAP 2, 3)
        wie_profiles = DistributionEngine._enrich_profiles(wie_profiles, actionable_movement)
        workload_groups, unmatched, classification_errors = WorkloadGrouper.group(
            actionable_movement, wie_profiles, pods
        )

        # Layer 3 — WorkloadSorter
        ordered = WorkloadSorter.sort(workload_groups, wie_profiles, plan)

        # Layer 4 — MigrationGroupBuilder
        # Budget is the number of actionable moves (no_capacity-blocked excluded).
        budget = {
            "pods":         len(actionable_movement),
            "nodes_create": sum(
                1 for n in (plan.get("node_plan") or [])
                if n.get("action") == "provision"
            ),
            "nodes_drain": sum(
                1 for n in (plan.get("node_plan") or [])
                if n.get("action") == "drain"
            ),
        }
        initial_budget = dict(budget)

        migration_groups: List[Dict[str, Any]] = []

        for wid in ordered:
            profile = wie_profiles.get(wid, {})
            steps   = workload_groups[wid]

            if budget["pods"] <= 0:
                migration_groups.append({
                    "group_id":   f"deferred-{wid}",
                    "workload_id": wid,
                    "type":       "DEFERRED",
                    "reason":     "movement_budget_exhausted",
                })
                continue

            wclass = WorkloadSorter._derive_class(profile)
            gtype = MigrationGroupBuilder.group_type(profile)
            if gtype == "SERIAL":
                group = MigrationGroupBuilder.build_serial(
                    wid, profile, steps, plan, budget
                )
            elif gtype == "BLUE_GREEN":
                group = MigrationGroupBuilder.build_blue_green(
                    wid, profile, steps, plan, budget
                )
            elif gtype == "ROLLING":
                group = MigrationGroupBuilder.build_rolling(
                    wid, profile, steps, plan, budget
                )
            else:
                group = MigrationGroupBuilder.build_batch(
                    wid, profile, steps, plan, budget
                )
            group["workload_class"] = wclass
            migration_groups.append(group)

        # Unmatched pods → generic BATCH group (never silently dropped)
        if unmatched:
            migration_groups.append(
                MigrationGroupBuilder.build_batch(
                    "unmatched", {}, unmatched, plan, budget
                )
            )

        # Layer 2b+2c — Dependency graph + parallel wave scheduling metadata
        dep_graph = DependencyGraphBuilder.build(
            workload_groups, wie_profiles, plan.get("node_plan") or []
        )
        parallel_waves = WaveBuilder.build(ordered, dep_graph, wie_profiles, migration_groups)

        # Layer 5 — logical role tagging + PreconditionSnapshotter
        tagged_plan = DistributionEngine._tag_logical_roles(plan.get("node_plan") or [])
        plan = dict(plan)
        plan["node_plan"] = tagged_plan

        snapshot = PreconditionSnapshotter.snapshot(plan, nodes, pods)

        manifest_id = "mfst-" + hashlib.sha256(
            f"{plan['feasibility'].get('plan_id', '')}{snapshot['snapshot_timestamp']}".encode()
        ).hexdigest()[:12]

        # Gap 6 — plan_status: derivable from whether provision entries have instance_type
        _prov = [n for n in (plan.get("node_plan") or []) if n.get("action") == "provision"]
        if not _prov:
            _plan_status = "no_action"
        elif all(n.get("instance_type") for n in _prov):
            _plan_status = "resolved"
        elif any(n.get("instance_type") for n in _prov):
            _plan_status = "partial"
        else:
            _plan_status = "draft"

        manifest = {
            "schema_version":          SCHEMA_VERSION,
            "manifest_id":             manifest_id,
            "plan_id":                 plan["feasibility"].get("plan_id"),
            "status":                  "READY",
            "plan_status":             _plan_status,
            "generated_at":            snapshot["snapshot_timestamp"],
            "expires_in_seconds":      MANIFEST_TTL_SECONDS,
            "workload_priority_order": ordered,
            "migration_groups":        migration_groups,
            "parallel_waves":          parallel_waves,
            "classification_errors":   classification_errors,
            "blocked_workloads": [
                {
                    "workload_id": e.get("workload"),
                    "reason":      e.get("reason"),
                }
                for e in (plan.get("validation_errors") or [])
            ],
            "budget_consumed": {
                "pods":         initial_budget["pods"]         - budget["pods"],
                "nodes_create": initial_budget["nodes_create"] - budget["nodes_create"],
                "nodes_drain":  initial_budget["nodes_drain"]  - budget["nodes_drain"],
            },
            "budget_remaining":      budget,
            "precondition_snapshot": snapshot,
            "node_plan":             plan.get("node_plan"),
            "node_layout":           plan.get("node_layout"),
            "anchor_plan":           plan.get("anchor_plan"),
            "cost_projection":       plan.get("cost_projection"),
        }

        # Persist to ManifestStore so ExecutionEngine can pick it up next auto_rebalancer cycle.
        # cluster_id must be embedded in feasibility by the caller (PPE sets it via plan_id prefix).
        cluster_id = plan["feasibility"].get("cluster_id")
        if cluster_id:
            try:
                from backend.services.execution_engine import ManifestStore
                ManifestStore.write(cluster_id, manifest,
                                    ttl=MANIFEST_TTL_SECONDS, db=db)
                logger.debug("DistributionEngine: manifest written to ManifestStore cluster=%s id=%s", cluster_id, manifest_id)
            except Exception as _ms_err:
                logger.warning("DistributionEngine: ManifestStore.write failed (non-fatal): %s", _ms_err)

        return manifest