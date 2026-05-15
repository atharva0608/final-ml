"""
InstanceSelector — Single-entry instance type resolver (Problems 6, 6a-6c, 19-23, 27-28, 30-31).

Called by InstanceSelectionService per provision entry.
PPE node_plan carries a *hint* (cloned type or None).
InstanceSelector replaces that hint with a DecisionEngineService-ranked result.

Correctness guarantees:
  AZ RESTRICTION (6b)     — allowed_azs is locked to provision_entry AZ; never overridden.
  CAPACITY TYPE (6c)      — explicit capacity_type field checked first; price-delta is fallback.
  POD DENSITY (6a)        — density filter raises DensityTransientError, never silently undersizes.
  HINT GATES (19)         — hint fallback requires: not blacklisted + density ok + risk gate.
  COST STRATEGY (20)      — cost_strategy from policy param only; stripped + warned from packing_context.
  TIMEOUT (23)            — de_timeout_ms with de_fallback policy ("fail" | "use_hint").
  MAX PODS CATALOG (27)   — catalog lookup first; heuristic is explicit fallback.
  HINT RISK CACHE (28)    — exec_cache may carry actual risk from prior DE result.
  SHARED EXECUTOR (30)    — class-level ThreadPoolExecutor; not per-call.
  EXEC CACHE (31)         — exec_cache dict scoped to resolve_all(); key=(az,cap,vcpu,mem).
"""

from __future__ import annotations

import atexit
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.core.logger import logger


# ── Shared executor (Problem 30) ─────────────────────────────────────────────
# One executor for the process lifetime; never re-created per resolve() call.
_DE_EXECUTOR: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="iss_de")
atexit.register(_DE_EXECUTOR.shutdown, wait=False)


# ── Exception hierarchy ───────────────────────────────────────────────────────

class ISError(Exception):
    """Base for all InstanceSelector errors."""


class TransientError(ISError):
    """DE unavailable or density failure — retry is safe."""
    def __init__(self, msg: str, retry_delay: int = 30):
        super().__init__(msg)
        self.retry_delay = retry_delay


class DensityTransientError(TransientError):
    """
    Problem 24 — annotated density failure.
    Carries best_max_pods_seen so _split_provision_entry() does not need a
    second DE call to compute N partitions.
    """
    def __init__(self, msg: str, retry_delay: int = 60,
                 best_max_pods_seen: Optional[int] = None):
        super().__init__(msg, retry_delay=retry_delay)
        self.best_max_pods_seen = best_max_pods_seen


class PermanentError(ISError):
    """No valid instance found after all fallbacks — caller must replan."""


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class InstanceResolution:
    instance_type:          str
    az:                     str
    ml_score:               float
    predicted_savings:      float
    risk_probability:       float
    source:                 str          # "de_ranked" | "ppe_hint" | "split_fallback"
    pod_density_score:      float = 0.0
    capacity_type_confirmed: bool = True


# ── InstanceSelector ──────────────────────────────────────────────────────────

class InstanceSelector:
    """
    Single-entry resolver.  See module docstring for correctness guarantees.
    """

    _K8S_MAX_PODS_HARD_CAP = 110
    RISK_SAFE_THRESHOLD_DEFAULT = 0.30

    def __init__(
        self,
        decision_engine,                   # DecisionEngineService
        de_timeout_ms: int = 2000,         # Problem 23
        de_fallback: str = "fail",         # "fail" | "use_hint"
    ):
        self.de            = decision_engine
        self.de_timeout_ms = de_timeout_ms
        self.de_fallback   = de_fallback

    # ── Static helpers ────────────────────────────────────────────────────────

    def _estimate_max_pods(self, instance_type: str, vcpu: Optional[int] = None) -> int:
        """
        Problem 27 — catalog lookup first, heuristic is explicit fallback.
        """
        try:
            catalog = getattr(self.de.ranking_service, "instance_catalog", {})
            catalog_val = catalog.get(instance_type, {}).get("max_pods") if catalog else None
            if catalog_val:
                logger.debug("instance_selector.max_pods_catalog_hit",
                             instance_type=instance_type, max_pods=catalog_val)
                return int(catalog_val)
        except Exception:
            pass

        if vcpu and vcpu > 0:
            heuristic = min(self._K8S_MAX_PODS_HARD_CAP, vcpu * 4 + 2)
            logger.debug("instance_selector.max_pods_heuristic_used",
                         instance_type=instance_type, vcpu=vcpu, heuristic=heuristic)
            return heuristic
        return self._K8S_MAX_PODS_HARD_CAP

    @staticmethod
    def _matches_capacity_type(pool: Dict, required_cap: str) -> bool:
        """
        Problem 6c — explicit capacity_type field first; price-delta fallback.
        """
        pool_cap = (pool.get("capacity_type") or "").lower().replace("ondemand", "on-demand")
        if pool_cap in ("spot", "on-demand"):
            return pool_cap == required_cap

        sp = pool.get("spot_price")
        od = pool.get("ondemand_price")
        if required_cap == "spot":
            return sp is not None and (od is None or sp < od)
        else:
            return od is not None and sp is None

    # ── Equivalent-shape resolver (Right-Sizing OFF) ─────────────────────────

    def _resolve_equivalent_shape(
        self,
        cluster_id: str,
        provision_entry: Dict,
        shape_anchor: str,
        az: str,
        cap_type: str,
        exec_cache: Optional[Dict] = None,
    ) -> InstanceResolution:
        """
        Right-Sizing OFF path (plan.md Layer 4 — equivalent_shape strategy).
        Preserves the current instance shape (family + size) and tries to migrate
        OD → Spot for the same shape. Falls back to same-shape OD if no Spot exists.
        ENI check skipped here — shape is already proven to fit the workload.
        ML scoring / resource-fit ranking are intentionally bypassed.
        """
        cap_norm = "spot" if "spot" in cap_type.lower() else "on-demand"

        # Get pool candidates for this AZ (reuse exec_cache if available)
        template = {"min_vcpu": 1, "min_memory": 1, "allowed_azs": [az]}
        cache_key = (az, "spot", 1, 1)
        if exec_cache is not None and cache_key in exec_cache:
            all_pools = list(exec_cache[cache_key])
        else:
            all_pools = self._call_de(cluster_id, template, True, "spot", shape_anchor)
            if exec_cache is not None:
                exec_cache[cache_key] = list(all_pools)

        # Filter to exact shape match
        same_shape = [p for p in all_pools if p.get("instance_type") == shape_anchor]

        # Prefer Spot of exact shape
        spot_match = [p for p in same_shape if self._matches_capacity_type(p, "spot")]
        if spot_match:
            p = spot_match[0]
            return InstanceResolution(
                instance_type=shape_anchor,
                az=az,
                ml_score=p.get("ml_score", 0.5),
                predicted_savings=p.get("predicted_savings", 0.0),
                risk_probability=p.get("risk_probability", 0.1),
                source="equivalent_shape_spot",
                pod_density_score=1.0,
                capacity_type_confirmed=True,
            )

        # Fall back to OD same shape (no migration possible for this shape)
        od_match = [p for p in same_shape if self._matches_capacity_type(p, "on-demand")]
        if od_match:
            return InstanceResolution(
                instance_type=shape_anchor,
                az=az,
                ml_score=0.5,
                predicted_savings=0.0,
                risk_probability=0.0,
                source="equivalent_shape_od_fallback",
                pod_density_score=1.0,
                capacity_type_confirmed=True,
            )

        # No DE data for this shape — use hint directly (safe: shape unchanged)
        logger.debug(
            "instance_selector.equivalent_shape_hint_fallback",
            cluster_id=cluster_id,
            shape_anchor=shape_anchor,
            az=az,
        )
        return InstanceResolution(
            instance_type=shape_anchor,
            az=az,
            ml_score=0.5,
            predicted_savings=0.0,
            risk_probability=0.0,
            source="equivalent_shape_hint",
            pod_density_score=1.0,
            capacity_type_confirmed=False,
        )

    # ── Main resolution ───────────────────────────────────────────────────────

    def resolve(
        self,
        cluster_id: str,
        provision_entry: Dict,
        diversify: bool = True,
        packing_context: Optional[Dict] = None,
        risk_threshold: Optional[float] = None,
        cost_strategy: Optional[str] = None,
        exec_cache: Optional[Dict] = None,     # Problem 31: execution-scoped cache
    ) -> InstanceResolution:
        """
        Returns InstanceResolution.  Raises TransientError or PermanentError.
        Branches on _strategy field (set by ISS from placement_policy):
          "equivalent_shape" — Right-Sizing OFF: preserve shape, prefer Spot
          "resource_fit"     — Right-Sizing ON:  full ML ranking (existing behavior)
        """
        az          = provision_entry["az"]                         # LOCKED — never override
        cap_type    = provision_entry.get("capacity_type", "spot")

        # Right-Sizing OFF path — bypass ML ranking entirely
        strategy     = provision_entry.get("_strategy", "resource_fit")
        shape_anchor = provision_entry.get("_shape_anchor")
        if strategy == "equivalent_shape" and shape_anchor:
            return self._resolve_equivalent_shape(
                cluster_id=cluster_id,
                provision_entry=provision_entry,
                shape_anchor=shape_anchor,
                az=az,
                cap_type=cap_type,
                exec_cache=exec_cache,
            )
        need_cpu_mc = float(provision_entry.get("required_cpu_millicores") or 2000)
        need_mem_gb = float(provision_entry.get("required_memory_bytes") or 8e9) / 1e9
        ppe_hint    = provision_entry.get("instance_type")

        # Problem 6a — required pods from BinPacker via packing_context
        required_pods = int((packing_context or {}).get("pod_count", 0))

        # Problem 20 — strip cost_strategy from packing_context
        if packing_context and "cost_strategy" in packing_context:
            logger.warning(
                "instance_selector.packing_context_cost_strategy_stripped",
                leaked_value=packing_context["cost_strategy"],
            )
            packing_context = {k: v for k, v in packing_context.items()
                               if k != "cost_strategy"}

        effective_strategy  = cost_strategy or "balanced"
        effective_threshold = risk_threshold if risk_threshold is not None \
                              else self.RISK_SAFE_THRESHOLD_DEFAULT

        # Problem 6b — AZ locked
        template = {
            "min_vcpu":    max(1, math.ceil(need_cpu_mc / 1000)),
            "min_memory":  max(1, math.ceil(need_mem_gb)),
            "allowed_azs": [az],
        }
        cap_norm = "spot" if "spot" in cap_type.lower() else "on-demand"

        # Problem 31 — exec_cache lookup
        cache_key = (az, cap_norm,
                     template["min_vcpu"], template["min_memory"])
        if exec_cache is not None and cache_key in exec_cache:
            ranked = list(exec_cache[cache_key])
        else:
            ranked = self._call_de(cluster_id, template, diversify, cap_norm, ppe_hint)
            if exec_cache is not None:
                exec_cache[cache_key] = list(ranked)

        before_cap_filter = len(ranked)

        # Step 2 — Capacity type filter (Problem 6c)
        ranked = [r for r in ranked if self._matches_capacity_type(r, cap_norm)]
        cap_type_confirmed = all(
            (r.get("capacity_type") or "").lower().replace("ondemand", "on-demand") == cap_norm
            for r in ranked
        )
        if before_cap_filter > 0 and not ranked:
            logger.warning("instance_selector.capacity_filter_removed_all",
                           before=before_cap_filter, required=cap_norm)

        # Step 3 — Pod-density filter (Problem 6a)
        best_max_pods_seen = 0
        density_filtered_out: List[Dict] = []
        if required_pods > 0 and ranked:
            density_ok: List[Dict] = []
            for r in ranked:
                vcpu     = r.get("vcpu") or None
                max_pods = self._estimate_max_pods(r["instance_type"], vcpu=vcpu)
                best_max_pods_seen = max(best_max_pods_seen, max_pods)
                r["_density_ratio"] = round(max_pods / required_pods, 2)
                if max_pods >= required_pods:
                    density_ok.append(r)
                else:
                    density_filtered_out.append(r)

            if density_ok:
                ranked = density_ok
            else:
                raise DensityTransientError(
                    f"InstanceSelector: all {len(density_filtered_out)} DE candidates have "
                    f"max_pods < required_pods={required_pods}",
                    retry_delay=60,
                    best_max_pods_seen=best_max_pods_seen or None,
                )

        # Step 4 — Cost strategy (Problem 20: from policy param only)
        ranked = self._apply_cost_strategy(ranked, effective_strategy, effective_threshold)

        # Step 5 — Best result
        if ranked:
            best     = ranked[0]
            vcpu     = best.get("vcpu") or None
            max_pods = self._estimate_max_pods(best["instance_type"], vcpu=vcpu)
            density_score = (max_pods / required_pods) if required_pods > 0 else 0.0
            logger.info("instance_selector.resolved", source="de_ranked",
                        instance_type=best["instance_type"], az=az,
                        ml_score=best.get("ml_score"),
                        risk=best.get("risk_probability"),
                        pod_density_score=round(density_score, 2),
                        capacity_type_confirmed=cap_type_confirmed)
            return InstanceResolution(
                instance_type=best["instance_type"],
                az=az,
                ml_score=best.get("ml_score", 0.0),
                predicted_savings=best.get("predicted_savings", 0.0),
                risk_probability=best.get("risk_probability", 0.0),
                source="de_ranked",
                pod_density_score=round(density_score, 2),
                capacity_type_confirmed=cap_type_confirmed,
            )

        # Step 6 — PPE hint fallback (Problem 19: three safety gates)
        if ppe_hint:
            return self._resolve_hint_fallback(
                cluster_id=cluster_id,
                az=az,
                ppe_hint=ppe_hint,
                required_pods=required_pods,
                effective_threshold=effective_threshold,
                before_cap_filter=before_cap_filter,
                density_filtered_out=density_filtered_out,
                exec_cache=exec_cache,
            )

        raise PermanentError(
            f"No valid instance type for cluster={cluster_id} az={az} cap={cap_type}. "
            f"DE returned {before_cap_filter} pools; all removed by filters. "
            f"PPE hint={ppe_hint} is None."
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_de(
        self,
        cluster_id: str,
        template: Dict,
        diversify: bool,
        cap_norm: str,
        ppe_hint: Optional[str],
    ) -> List[Dict]:
        """
        Problem 23 — wraps rank_for_template with timeout.
        Uses class-level executor (Problem 30).
        """
        timeout_s  = self.de_timeout_ms / 1000.0
        fut = _DE_EXECUTOR.submit(
            self.de.rank_for_template,
            cluster_id=cluster_id,
            template=template,
            limit=10,
            diversify=diversify,
        )
        try:
            return fut.result(timeout=timeout_s)
        except _FutureTimeout:
            logger.warning("instance_selector.de_timeout",
                           timeout_ms=self.de_timeout_ms,
                           fallback=self.de_fallback)
            if self.de_fallback == "use_hint":
                return []
            raise TransientError(
                f"DecisionEngineService timed out after {timeout_s}s",
                retry_delay=30,
            )
        except Exception as e:
            logger.warning("instance_selector.de_unavailable", error=str(e))
            raise TransientError(f"DecisionEngineService unavailable: {e}", retry_delay=30)

    def _apply_cost_strategy(
        self,
        ranked: List[Dict],
        strategy: str,
        threshold: float,
    ) -> List[Dict]:
        """Problem 20: cost_strategy from policy only."""
        if strategy == "savings_first":
            return sorted(ranked, key=lambda r: r.get("predicted_savings", 0.0), reverse=True)
        if strategy == "risk_first":
            return ranked  # DE ordering preserved
        # "balanced" (default)
        safe = [r for r in ranked if r.get("risk_probability", 1.0) < threshold]
        if safe:
            unsafe = [r for r in ranked if r.get("risk_probability", 1.0) >= threshold]
            return (sorted(safe, key=lambda r: r.get("predicted_savings", 0.0), reverse=True)
                    + unsafe)
        return ranked

    def _resolve_hint_fallback(
        self,
        cluster_id: str,
        az: str,
        ppe_hint: str,
        required_pods: int,
        effective_threshold: float,
        before_cap_filter: int,
        density_filtered_out: List[Dict],
        exec_cache: Optional[Dict],
    ) -> InstanceResolution:
        """
        Problem 19 — three safety gates before using PPE hint.
        Problem 28 — use actual risk from exec_cache if hint appeared in DE results.
        """
        try:
            from backend.models.cluster import Cluster
            from backend.core.database import SessionLocal
            db = SessionLocal()
            try:
                cl = db.query(Cluster).filter(Cluster.id == cluster_id).first()
                region = cl.region if cl else "ap-south-1"
            finally:
                db.close()
        except Exception:
            region = "ap-south-1"

        bl, _ = self.de.blacklist_service.is_blacklisted(ppe_hint, az, region)
        if bl:
            logger.warning("instance_selector.hint_fallback_rejected",
                           ppe_hint=ppe_hint, reason="blacklisted")
            raise PermanentError(
                f"PPE hint {ppe_hint} is blacklisted — no valid instance for "
                f"cluster={cluster_id} az={az}"
            )

        hint_max_pods    = self._estimate_max_pods(ppe_hint)
        hint_density_ok  = (required_pods == 0) or (hint_max_pods >= required_pods)
        if not hint_density_ok:
            logger.warning("instance_selector.hint_fallback_rejected",
                           ppe_hint=ppe_hint, reason="density_fail",
                           hint_max_pods=hint_max_pods, required_pods=required_pods)
            raise PermanentError(
                f"PPE hint {ppe_hint} fails density check: max_pods={hint_max_pods} "
                f"< required={required_pods}"
            )

        # Problem 28 — look up actual risk from exec_cache
        hint_risk = 1.0
        hint_ml   = 0.0
        if exec_cache:
            for cached_results in exec_cache.values():
                for pool in cached_results:
                    if pool.get("instance_type") == ppe_hint:
                        hint_risk = pool.get("risk_probability", 1.0)
                        hint_ml   = pool.get("ml_score", 0.0)
                        break

        hint_risk_ok = hint_risk <= (effective_threshold * 2)
        if not hint_risk_ok:
            logger.warning("instance_selector.hint_fallback_rejected",
                           ppe_hint=ppe_hint, reason="risk_too_high",
                           hint_risk=hint_risk,
                           threshold_x2=effective_threshold * 2)
            raise PermanentError(
                f"PPE hint {ppe_hint} risk={hint_risk:.2f} exceeds "
                f"risk_threshold*2={effective_threshold * 2:.2f}"
            )

        hint_density = hint_max_pods / required_pods if required_pods > 0 else 0.0
        logger.warning("instance_selector.fallback_to_hint",
                       ppe_hint=ppe_hint,
                       density_ok=hint_density_ok, risk_ok=hint_risk_ok)
        return InstanceResolution(
            instance_type=ppe_hint,
            az=az,
            ml_score=hint_ml,
            predicted_savings=0.0,
            risk_probability=hint_risk,
            source="ppe_hint",
            pod_density_score=round(hint_density, 2),
            capacity_type_confirmed=False,
        )
