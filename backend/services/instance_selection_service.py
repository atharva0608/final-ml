"""
InstanceSelectionService — Instance Selection layer facade (Problems 7-18, 24-26).

Called by DistributionEngine.build() — NOT by ExecutionEngine directly.
EE receives this via optional injection for mid-run pool failure retry only (Problem 11).

Responsibilities:
  - Load cluster placement_policy (Problems 10, 15).
  - Batch resolve instance_type across full node_plan via InstanceSelector.
  - Escalating retry on density failure: attempt 0 → 1 (wider CPU) → 2 (split) (Problem 8).
  - N-partition split-node fallback based on max_pods constraint (Problems 9, 12, 14, 18).
  - Propagate DensityTransientError.best_max_pods_seen to split (Problem 24).
  - Convert split-child TransientError → PermanentError (Problem 25).
  - Append-only audit via ExecutionOverrideStore (Problem 26).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.services.instance_selector import (
    DensityTransientError,
    InstanceResolution,
    InstanceSelector,
    PermanentError,
    TransientError,
)


class InstanceSelectionService:
    """
    Facade for resolving instance types across an entire node_plan.
    See module docstring.
    """

    MAX_SPLIT_DEPTH = 1  # Problem 14: hard cap — split entries may NOT split again

    def __init__(self, selector: InstanceSelector, db: Session):
        self.selector = selector
        self.db       = db

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve_all(
        self,
        cluster_id: str,
        node_plan: List[Dict],
        diversify: bool = True,
    ) -> List[Dict]:
        """
        Resolve instance_type for every action="provision" entry.
        Non-provision entries pass through unchanged.
        May return MORE entries than input if split-node fallback triggered.
        """
        resolved: List[Dict] = []
        exec_cache: Dict = {}   # Problem 31: scoped to this invocation, discarded after

        for entry in node_plan:
            if entry.get("action") != "provision":
                resolved.append(entry)
                continue

            workload_class = entry.get("workload_class")  # set by WIE (Problem 15)
            policy = self._load_placement_policy(cluster_id, workload_class=workload_class)
            # Enforce capacity type: spot provision entries must not receive OD instances
            # and OD provision entries must not receive spot instances.
            required_cap = entry.get("capacity_type")
            if required_cap:
                policy["required_capacity_type"] = required_cap

            enriched = self._resolve_with_escalation(
                cluster_id=cluster_id,
                entry=entry,
                policy=policy,
                diversify=diversify,
                exec_cache=exec_cache,
            )
            resolved.extend(enriched)

        return resolved

    # ── Escalating retry (Problem 8) ─────────────────────────────────────────

    def _resolve_with_escalation(
        self,
        cluster_id: str,
        entry: Dict,
        policy: Dict,
        diversify: bool,
        exec_cache: Dict,
    ) -> List[Dict]:
        """
        attempt 0: original template
        attempt 1: wider CPU (×1.5) — pushes DE toward higher-ENI instance families
        attempt 2: split-node fallback

        DensityTransientError carries best_max_pods_seen (Problem 24) — passed to split.
        """
        original_pods   = int(entry.get("pod_count") or 0)
        original_cpu_mc = float(entry.get("required_cpu_millicores") or 2000)
        last_density_err: Optional[DensityTransientError] = None

        for attempt in range(3):
            if attempt == 2:
                max_pods_hint = (
                    last_density_err.best_max_pods_seen
                    if last_density_err and last_density_err.best_max_pods_seen
                    else None
                )
                return self._split_provision_entry(
                    entry=entry,
                    policy=policy,
                    cluster_id=cluster_id,
                    diversify=diversify,
                    exec_cache=exec_cache,
                    max_pods_per_node_hint=max_pods_hint,
                )

            packing_context = {
                "pod_count":        original_pods,
                "vcpu_scale_factor": 1.5 if attempt == 1 else 1.0,
            }
            attempt_entry = dict(entry)
            if attempt == 1:
                attempt_entry["required_cpu_millicores"] = math.ceil(original_cpu_mc * 1.5)

            # Right-sizing toggle: if disabled, lock to equivalent_shape of current instance
            if not policy.get("right_sizing_enabled", False):
                attempt_entry["_strategy"]     = "equivalent_shape"
                attempt_entry["_shape_anchor"] = entry.get("instance_type")
            else:
                attempt_entry["_strategy"]     = "resource_fit"
                attempt_entry["_shape_anchor"] = None

            try:
                resolution = self.selector.resolve(
                    cluster_id=cluster_id,
                    provision_entry=attempt_entry,
                    diversify=diversify,
                    packing_context=packing_context,
                    risk_threshold=policy.get("risk_threshold",
                                              InstanceSelector.RISK_SAFE_THRESHOLD_DEFAULT),
                    cost_strategy=policy.get("cost_strategy", "balanced"),
                    exec_cache=exec_cache,
                )
                # Note: capacity_type filtering is enforced inside InstanceSelector.resolve()
                # via provision_entry["capacity_type"] (Step 2 — Problem 6c).
                # required_capacity_type in policy is kept for audit/logging only.
                result = dict(entry)
                result["instance_type"]      = resolution.instance_type
                result["_resolution_source"] = resolution.source
                result["_ml_score"]          = resolution.ml_score
                result["_predicted_savings"] = resolution.predicted_savings
                result["_risk_probability"]  = resolution.risk_probability
                result["_pod_density_score"] = resolution.pod_density_score
                return [result]

            except DensityTransientError as e:
                last_density_err = e
                logger.warning("iss.density_retry",
                               cluster_id=cluster_id, attempt=attempt,
                               best_max_pods_seen=e.best_max_pods_seen,
                               reason=str(e))
                continue

            except TransientError as e:
                logger.warning("iss.retry",
                               cluster_id=cluster_id, attempt=attempt, reason=str(e))
                continue

        raise PermanentError("InstanceSelectionService: escalation exhausted without result")

    # ── Split-node fallback (Problems 9, 12, 14, 18, 24, 25) ─────────────────

    def _split_provision_entry(
        self,
        entry: Dict,
        policy: Dict,
        cluster_id: str,
        diversify: bool,
        exec_cache: Dict,
        max_pods_per_node_hint: Optional[int] = None,
    ) -> List[Dict]:
        """
        N-partition split using actual pod groupings from packed_pods (Problem 12).
        Falls back to arithmetic partitioning with WARNING if packed_pods absent (legacy).
        """
        # Problem 14 — depth guard
        current_depth = int(entry.get("_split_depth", 0))
        if current_depth >= self.MAX_SPLIT_DEPTH:
            raise PermanentError(
                f"InstanceSelectionService: split depth {current_depth} >= "
                f"MAX_SPLIT_DEPTH ({self.MAX_SPLIT_DEPTH}) for node "
                f"{entry.get('node_name')}. Cannot split further — escalate to replanning."
            )

        total_pods  = int(entry.get("pod_count") or 1)
        packed_pods = entry.get("packed_pods")

        # Problem 18 — N partitions from max_pods constraint.
        # Use hint from DensityTransientError (Problem 24) — no second DE call.
        if max_pods_per_node_hint and max_pods_per_node_hint > 0:
            max_pods_per_node = max_pods_per_node_hint
        else:
            max_pods_per_node = self.selector._K8S_MAX_PODS_HARD_CAP

        n_partitions = max(2, math.ceil(total_pods / max_pods_per_node))

        if packed_pods:
            chunk       = math.ceil(len(packed_pods) / n_partitions)
            groups_pods = [packed_pods[i:i + chunk]
                           for i in range(0, len(packed_pods), chunk)]
            groups_pods = [g for g in groups_pods if g]

            halves = []
            for pod_group in groups_pods:
                h_cpu = sum(p.get("cpu_millicores", 0) for p in pod_group)
                h_mem = sum(p.get("memory_bytes",  0) for p in pod_group)
                halves.append((h_cpu, h_mem, len(pod_group), pod_group))
        else:
            logger.warning(
                "iss.split_arithmetic_fallback",
                cluster_id=cluster_id,
                node_name=entry.get("node_name"),
                n_partitions=n_partitions,
                reason="packed_pods absent — arithmetic split used",
            )
            base_cpu  = float(entry.get("required_cpu_millicores") or 2000)
            base_mem  = float(entry.get("required_memory_bytes")   or 8e9)
            part_cpu  = math.ceil(base_cpu / n_partitions)
            part_mem  = math.ceil(base_mem / n_partitions)
            part_pods = max(1, math.ceil(total_pods / n_partitions))
            halves    = [(part_cpu, part_mem, part_pods, None)] * n_partitions

        results: List[Dict] = []
        for idx, (h_cpu, h_mem, h_pod_count, h_pod_group) in enumerate(halves):
            half_entry = dict(entry)
            half_entry["node_name"]               = (entry.get("node_name", "provision")
                                                      + f"-s{idx + 1}")
            half_entry["required_cpu_millicores"] = h_cpu
            half_entry["required_memory_bytes"]   = h_mem
            half_entry["pod_count"]               = h_pod_count
            half_entry["packed_pods"]             = h_pod_group
            half_entry["_split_depth"]            = current_depth + 1
            half_entry["_split_from"]             = entry.get("node_name")

            # Problem 25 — split children: TransientError → PermanentError immediately.
            try:
                resolution = self.selector.resolve(
                    cluster_id=cluster_id,
                    provision_entry=half_entry,
                    diversify=diversify,
                    packing_context={"pod_count": h_pod_count},
                    risk_threshold=policy.get("risk_threshold",
                                              InstanceSelector.RISK_SAFE_THRESHOLD_DEFAULT),
                    cost_strategy=policy.get("cost_strategy", "balanced"),
                    exec_cache=exec_cache,
                )
            except TransientError as e:
                raise PermanentError(
                    f"InstanceSelectionService: split child {half_entry['node_name']} "
                    f"resolution failed — unrecoverable at depth {current_depth + 1}: {e}"
                ) from e

            half_entry["instance_type"]      = resolution.instance_type
            half_entry["_resolution_source"] = "split_fallback"
            half_entry["_risk_probability"]  = resolution.risk_probability
            half_entry["_ml_score"]          = resolution.ml_score
            results.append(half_entry)

        logger.warning(
            "iss.split_triggered",
            cluster_id=cluster_id,
            original_node=entry.get("node_name"),
            split_depth=current_depth + 1,
            n_partitions=len(results),
            max_pods_per_node=max_pods_per_node,
            split_mode="pod_groups" if packed_pods else "arithmetic",
            groups=[(r["pod_count"], r["instance_type"]) for r in results],
        )
        return results

    # ── Placement policy loader (Problems 10, 15) ─────────────────────────────

    def _load_placement_policy(
        self,
        cluster_id: str,
        workload_class: Optional[str] = None,
    ) -> Dict:
        """
        Merge order: service defaults → cluster policy → workload_class override.
        workload_class set by WIE: "stateful" | "stateless" | "mixed" | None.
        """
        raw: Dict = {}
        try:
            from backend.models.cluster import Cluster
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster and hasattr(cluster, "placement_policy") and cluster.placement_policy:
                raw = cluster.placement_policy
        except Exception as e:
            logger.debug("iss.placement_policy_load_failed", error=str(e))

        policy = {
            "cost_strategy":       raw.get("cost_strategy", "balanced"),
            "risk_threshold":      float(raw.get("risk_threshold",
                                            InstanceSelector.RISK_SAFE_THRESHOLD_DEFAULT)),
            "right_sizing_enabled": bool(raw.get("right_sizing_enabled", False)),
        }

        # Workload-class overrides (Problem 15)
        overrides_map = raw.get("workload_overrides") or {}
        builtin_defaults = {
            "stateful":  {"cost_strategy": "risk_first",    "risk_threshold": 0.10},
            "stateless": {"cost_strategy": "savings_first", "risk_threshold": 0.40},
            "mixed":     {"cost_strategy": "balanced",      "risk_threshold": 0.25},
            "anchor":    {"cost_strategy": "risk_first",    "risk_threshold": 0.10},
        }
        if workload_class:
            if workload_class in overrides_map:
                override = overrides_map[workload_class]
                if "cost_strategy" in override:
                    policy["cost_strategy"] = override["cost_strategy"]
                if "risk_threshold" in override:
                    policy["risk_threshold"] = float(override["risk_threshold"])
                policy["_workload_class_override_applied"] = workload_class
            elif workload_class in builtin_defaults:
                policy.update(builtin_defaults[workload_class])
                policy["_workload_class_override_applied"] = f"{workload_class}_builtin"

        return policy