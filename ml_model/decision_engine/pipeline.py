"""
Decision Engine Pipeline — Main Entry Point
=============================================
Source: backend/core/decision_engine.py

PURPOSE
-------
Orchestrates the full 15-step decision pipeline for spot pool optimization.
This is the "brain" of the ML system — it decides WHETHER to execute a
pool switch and WHICH pool to switch to.

HOW TO USE
-----------
    from ml_model.decision_engine.pipeline import DecisionEngine

    engine = DecisionEngine(redis_client, db_session)
    result = engine.evaluate_action_plan(
        cluster_id="prod-cluster",
        current_pool={
            "instance_type": "m5.large", "az": "us-east-1a",
            "predicted_savings": 0.6, "risk_probability": 0.05,
            "region": "us-east-1"
        },
        candidate_pools=[
            {"instance_type": "c5.large", "az": "us-east-1b",
             "predicted_savings": 0.72, "risk_probability": 0.08,
             "normalized_volatility": 0.15, "capacity_age_minutes": 10,
             "model_version": "6"},
            ...
        ],
        action_type="POOL_SWITCH"
    )

    if result["approved"]:
        # Pass recommendation to Execution Engine
        recommendation = result["recommendation"]
        print(f"Switch to {recommendation['pool']['instance_type']}:{recommendation['pool']['az']}")
        print(f"EV improvement: {result['delta']:.4f}")
    else:
        print(f"Action blocked at step {result['step_completed']}: {result['reason']}")

FULL 15-STEP PIPELINE
----------------------

  STEP 1:  Cluster cooldown check
           Source: 03_cooldown_guard.py → CooldownController.can_switch()
           Blocks: Recent action within last 30 min

  STEP 1b: Pricing freshness check
           Source: 06_capacity_validator.py → check_pricing_freshness()
           Blocks: Regional pricing data older than 15 minutes

  STEP 2:  Pool cooldown check (per candidate)
           Source: 03_cooldown_guard.py → CooldownController.can_reuse_pool()
           Removes: Candidates in 30-min post-use cooldown

  STEP 2b: Node classification fetch
           Source: 04_workload_classifier.py → WorkloadInspector.get_cached_classification()
           Blocks: Classification cache missing (scanner must run first)

  STEP 2c: Filter STATELESS_ELIGIBLE nodes
           Source: 04_workload_classifier.py → WorkloadInspector.filter_stateless_nodes()
           Blocks: No eligible nodes (all stateful or system-protected)

  STEP 3:  Model version validation (soft — logs warning, doesn't block)
           Ensures candidates were scored by current model (regressor_6.onnx)

  STEP 4:  Load optimization mode (COST_FIRST / BALANCED / NO_DOWNTIME_FIRST)
           Source: 05_risk_filter.py → get_optimization_profile()
           Reads from Redis cache or falls back to BALANCED

  STEP 5:  Load global rankings
           Source: Intelligence Layer (ascpai_worker.py)
           Reads: spot:global_rankings:{region} from Redis
           Blocks: Rankings not available (intelligence layer not running)

  STEP 6:  Three-layer risk ceiling filter
           Source: 05_risk_filter.py → compute_effective_risk_ceiling()
           Layer 1: Optimization mode ceiling (10/20/25%)
           Layer 2: Volatility adjustment (-5% if volatile)
           Layer 3: Trust-phase override (Phase 0/1 = stricter)
           Removes: Candidates exceeding effective ceiling

  STEP 7:  Capacity freshness staleness penalty
           Source: 06_capacity_validator.py → apply_capacity_staleness_penalty()
           Effect: Reduces predicted_savings by 5% for stale capacity data

  STEP 8:  (Volatility guard — handled in Step 6)

  STEP 9:  Re-score candidates with full economic EV model
           Source: 07_pool_scorer.py → score_candidates_with_full_ev()
           Uses: 02_ev_model.py → evaluate_candidate_ev()
           Reads: Live DryRun failure rate from Redis (dynamic capacity risk)
           Removes: Candidates with EV ≤ 0 (costs more than saves)

  STEP 10: Score current pool (simple EV, no migration cost)
           Source: 10_delta_selector.py → compute_current_pool_ev()

  STEP 11: Apply template + Karpenter filters
           Source: 08_template_filter.py → apply_template_filter() + apply_karpenter_filter()
           Removes: Pools not in template whitelist, blacklisted pools, wrong architecture

  STEP 12: Apply diversity constraints
           Source: 09_diversity_check.py → DiversityEnforcer.check_candidate()
           Removes: Pools that would over-concentrate a family or AZ

  STEP 13: Delta threshold check
           Source: 10_delta_selector.py → apply_delta_threshold()
           Blocks: Best candidate EV improvement < delta_threshold (3/5/8%)

  STEP 14: Select best candidate and APPROVE
           Source: 10_delta_selector.py → build_approval_result()
           Returns: Full approval result with recommendation for Execution Engine

EXECUTION ENGINE HANDOFF
-------------------------
After Step 14 APPROVES, the recommendation dict is passed to:
  ml_model/execution_engine/01_action_queue.py → create AgentAction records
  ml_model/execution_engine/02_command_dispatcher.py → send to agent
  ml_model/execution_engine/03_k8s_actuator.py → cordon + drain + provision
"""

import json
from datetime import datetime
from typing import Dict, List, Optional


# ============================================================================
# OPTIMIZATION PROFILES (from 05_risk_filter.py — duplicated here for reference)
# ============================================================================

OPTIMIZATION_PROFILES = {
    "COST_FIRST":        {"risk_ceiling": 0.25, "delta_threshold": 0.03, "max_family_ratio": 0.4, "max_az_ratio": 0.5},
    "BALANCED":          {"risk_ceiling": 0.20, "delta_threshold": 0.05, "max_family_ratio": 0.4, "max_az_ratio": 0.5},
    "NO_DOWNTIME_FIRST": {"risk_ceiling": 0.10, "delta_threshold": 0.08, "max_family_ratio": 0.3, "max_az_ratio": 0.4},
}
DEFAULT_PROFILE = "BALANCED"
CURRENT_MODEL_VERSION = "6"  # Must match regressor_6.onnx
ITN_BYPASS_ENABLED = True    # Allow emergency bypass of cooldowns for spot interruptions


# ============================================================================
# DECISION ENGINE
# ============================================================================

class DecisionEngine:
    """
    15-step policy pipeline for spot pool optimization decisions.

    Integrates:
      - CooldownController (Steps 1-2)    — prevents action flapping
      - WorkloadInspector (Steps 2b-2c)   — node classification
      - Risk filter (Step 6)              — three-layer risk ceiling
      - EV model (Step 9)                 — full economic scoring
      - DiversityEnforcer (Step 12)       — instance family + AZ diversity
      - Delta selector (Steps 13-14)      — anti-micro-switch threshold

    Each step returns early if blocked, with reason string for observability.
    """

    def __init__(self, redis, db):
        """
        Args:
            redis: Redis client (from backend.core.redis_client)
            db:    SQLAlchemy database session
        """
        self.redis = redis
        self.db = db

        # Sub-services (imported from backend for production use)
        # In ml_model/ these are documented — see individual step files
        from backend.services.cooldown_controller import CooldownController
        from backend.services.diversity_enforcer import DiversityEnforcer
        from backend.services.workload_inspector import WorkloadInspector
        from backend.services.blacklist_service import BlacklistService

        self.cooldown = CooldownController(redis)
        self.diversity = DiversityEnforcer(redis)
        self.workload = WorkloadInspector(redis)
        self.blacklist = BlacklistService(redis)

    def evaluate_action_plan(
        self,
        cluster_id: str,
        current_pool: Dict,
        candidate_pools: List[Dict],
        action_type: str = "POOL_SWITCH",
        optimization_mode: Optional[str] = None,
        template_id: Optional[str] = None,
        karpenter_filters: Optional[Dict] = None,
        cluster_node_distribution: Optional[Dict] = None,
        total_nodes: int = 0,
        is_emergency: bool = False
    ) -> Dict:
        """
        Run the full 15-step decision pipeline.

        Args:
            cluster_id:                Cluster identifier
            current_pool:              Current pool dict with instance_type, az,
                                       predicted_savings, risk_probability, region
            candidate_pools:           ML-ranked pool candidates (from Intelligence Layer)
            action_type:               "POOL_SWITCH" (default)
            optimization_mode:         Override mode. None = read from Redis/DB
            template_id:               Node template UUID for instance family filters
            karpenter_filters:         Karpenter NodePool requirement constraints
            cluster_node_distribution: {"family_counts": {}, "az_counts": {}}
            total_nodes:               Total cluster node count (for diversity ratios)
            is_emergency:              True = ITN notice, bypass all cooldowns

        Returns:
            Result dict with "approved" bool, "recommendation" (if approved),
            "reason" (why blocked, if rejected), and debug fields.
            See 10_delta_selector.py for full schema.
        """
        start_time = datetime.utcnow()

        # ── STEP 1: Cluster cooldown ──────────────────────────────────────────
        # (Documented in 03_cooldown_guard.py)
        if not is_emergency:
            can_switch, remaining = self.cooldown.can_switch(cluster_id)
            if not can_switch:
                self._emit_metric("decision.rejected.cooldown", cluster_id)
                return self._reject(f"Cluster cooldown active ({remaining}s remaining)", "1_cluster_cooldown")

        # ── STEP 1b: Pricing freshness ────────────────────────────────────────
        # (Documented in 06_capacity_validator.py)
        if not is_emergency:
            region = current_pool.get("region", "us-east-1")
            is_fresh, staleness_min = self._check_pricing_freshness(region)
            if not is_fresh:
                self._emit_metric("decision.rejected.pricing_stale", cluster_id)
                return self._reject(f"Pricing data stale ({staleness_min:.0f} min old, max 15 min)", "1b_pricing_freshness")

        # ── STEP 2: Pool cooldowns (per candidate) ────────────────────────────
        # (Documented in 03_cooldown_guard.py)
        valid_candidates = []
        for pool in candidate_pools:
            pool_key = f"{pool['instance_type']}:{pool['az']}"
            can_reuse, remaining = self.cooldown.can_reuse_pool(pool_key)
            if can_reuse or (is_emergency and ITN_BYPASS_ENABLED):
                valid_candidates.append(pool)

        if not valid_candidates:
            self._emit_metric("decision.rejected.all_pools_cooled", cluster_id)
            return self._reject("All candidate pools in cooldown", "2_pool_cooldown")

        # ── STEP 2b: Node classification ─────────────────────────────────────
        # (Documented in 04_workload_classifier.py)
        classification = self.workload.get_cached_classification(cluster_id)
        if not classification:
            self._emit_metric("decision.rejected.no_classification", cluster_id)
            return self._reject("Node classification unavailable (WorkloadInspector scan required)", "2b_node_classification")

        # ── STEP 2c: Filter STATELESS_ELIGIBLE nodes ──────────────────────────
        from backend.services.workload_inspector import NodeStatus
        stateless_nodes = [n for n, s in classification.items() if s == NodeStatus.STATELESS_ELIGIBLE]
        if not stateless_nodes:
            self._emit_metric("decision.rejected.no_stateless_nodes", cluster_id)
            return self._reject("No STATELESS_ELIGIBLE nodes found (all nodes protected)", "2c_stateless_filter")

        # ── STEP 3: Model version validation (soft — warn only) ───────────────
        for pool in valid_candidates:
            if pool.get("model_version", "unknown") != CURRENT_MODEL_VERSION:
                pass  # Log warning, don't block (ITN_BYPASS_ENABLED)

        # ── STEP 4: Load optimization mode ───────────────────────────────────
        # (Documented in 05_risk_filter.py)
        if not optimization_mode:
            optimization_mode = self._get_cluster_optimization_mode(cluster_id)
        profile = OPTIMIZATION_PROFILES.get(optimization_mode, OPTIMIZATION_PROFILES[DEFAULT_PROFILE])

        # ── STEP 5: Load global rankings ──────────────────────────────────────
        region = current_pool.get("region", "us-east-1")
        global_rankings = self._load_global_rankings(region)
        if not global_rankings:
            self._emit_metric("decision.rejected.no_rankings", cluster_id)
            return self._reject("Global rankings unavailable (Intelligence Layer required)", "5_global_rankings")

        # ── STEP 6: Three-layer risk ceiling ──────────────────────────────────
        # (Documented in 05_risk_filter.py)
        risk_ceiling = profile["risk_ceiling"]
        if self._check_volatility_regime(region):
            risk_ceiling += profile.get("volatility_ceiling_adjustment", -0.05)
        try:
            from backend.services.optimizer_coordinator import OptimizerCoordinator
            trust = OptimizerCoordinator(self.db, self.redis).get_cluster_trust_phase(cluster_id)
            trust_ceiling = trust.get("risk_ceiling_override")
            if trust_ceiling is not None:
                risk_ceiling = min(risk_ceiling, trust_ceiling)
        except Exception:
            pass

        valid_candidates = [p for p in valid_candidates if p.get("risk_probability", 1.0) <= risk_ceiling]
        if not valid_candidates:
            self._emit_metric("decision.rejected.risk_ceiling", cluster_id)
            return self._reject(f"All candidates exceed risk ceiling ({risk_ceiling:.2%})", "6_risk_ceiling")

        # ── STEP 7: Capacity freshness staleness penalty ──────────────────────
        # (Documented in 06_capacity_validator.py)
        for pool in valid_candidates:
            if pool.get("capacity_age_minutes", 0) > profile.get("capacity_freshness_min", 80):
                pool["predicted_savings"] = pool.get("predicted_savings", 0.0) * profile.get("staleness_penalty", 0.95)
                pool["staleness_penalty_applied"] = True

        # ── STEP 8: Volatility guard (applied in Step 6) ─────────────────────
        pass

        # ── STEP 9: Re-score all pools with full economic EV model ────────────
        # (Documented in 07_pool_scorer.py + 02_ev_model.py)
        from backend.core.ev_model import evaluate_candidate_ev, get_dynamic_capacity_failure_probability
        ev_eligible = []
        for pool in valid_candidates:
            pool_id = f"{pool.get('instance_type', '')}:{pool.get('az', '')}"
            try:
                cap_fail_prob = get_dynamic_capacity_failure_probability(self.redis, pool_id, region)
                ev_breakdown = evaluate_candidate_ev(
                    savings=pool.get("predicted_savings", 0.0),
                    final_risk=pool.get("risk_probability", 0.0),
                    normalized_volatility=pool.get("normalized_volatility", 0.0),
                    capacity_failure_probability=cap_fail_prob,
                )
                if ev_breakdown["is_eligible"]:
                    pool["expected_value"] = ev_breakdown["ev"]
                    pool["ev_breakdown"] = ev_breakdown
                    ev_eligible.append(pool)
            except Exception:
                pool["expected_value"] = 0.0
        valid_candidates = ev_eligible

        # ── STEP 10: Score current pool ───────────────────────────────────────
        current_savings = current_pool.get("predicted_savings", 0.0)
        current_risk = current_pool.get("risk_probability", 0.0)
        try:
            current_pool_ev = (
                current_savings * (1.0 - current_risk)
                if 0.0 <= current_savings <= 1.0 and 0.0 <= current_risk <= 1.0
                else 0.0
            )
        except Exception:
            current_pool_ev = 0.0

        # ── STEP 11: Template + Karpenter filters ─────────────────────────────
        # (Documented in 08_template_filter.py)
        if template_id:
            valid_candidates = self._apply_template_filters(valid_candidates, template_id)
        if karpenter_filters:
            valid_candidates = self._apply_karpenter_filters(valid_candidates, karpenter_filters)
        if not valid_candidates:
            self._emit_metric("decision.rejected.template_filters", cluster_id)
            return self._reject("No candidates pass template/Karpenter filters", "11_template_filters", current_pool_ev)

        # ── STEP 12: Diversity check ──────────────────────────────────────────
        # (Documented in 09_diversity_check.py)
        if cluster_node_distribution and not (is_emergency and ITN_BYPASS_ENABLED):
            diversity_passed = []
            for pool in valid_candidates:
                passes, _ = self.diversity.check_candidate(
                    candidate_pool=pool,
                    cluster_node_distribution=cluster_node_distribution,
                    total_nodes=total_nodes,
                    max_family_ratio=profile["max_family_ratio"],
                    max_az_ratio=profile["max_az_ratio"],
                )
                if passes:
                    diversity_passed.append(pool)
            valid_candidates = diversity_passed

        if not valid_candidates:
            if current_pool_ev >= 0.5:
                return self._reject("No diversity-compliant candidates (holding safe current pool)", "12_diversity_deadlock", current_pool_ev)
            self._emit_metric("decision.rejected.diversity", cluster_id)
            return self._reject("No candidates pass diversity constraints", "12_diversity", current_pool_ev)

        # ── STEP 13: Delta threshold check ────────────────────────────────────
        # (Documented in 10_delta_selector.py)
        valid_candidates.sort(key=lambda p: p.get("expected_value", 0.0), reverse=True)
        best_candidate = valid_candidates[0]
        best_candidate_ev = best_candidate.get("expected_value", 0.0)
        delta = best_candidate_ev - current_pool_ev
        delta_threshold = profile["delta_threshold"]

        if delta < delta_threshold:
            self._emit_metric("decision.rejected.delta_threshold", cluster_id)
            return self._reject(
                f"Delta {delta:.4f} below threshold {delta_threshold:.4f}",
                "13_delta_threshold", current_pool_ev, best_candidate_ev, delta
            )

        # ── STEP 14: Approve! ─────────────────────────────────────────────────
        self._emit_metric("decision.approved", cluster_id)
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "approved": True,
            "reason": "Action approved",
            "recommendation": {
                "pool": best_candidate,
                "action_type": action_type,
                "current_pool": current_pool,
                "ev_improvement": delta,
                "optimization_mode": optimization_mode,
                "timestamp": datetime.utcnow().isoformat()
            },
            "current_pool_ev": current_pool_ev,
            "best_candidate_ev": best_candidate_ev,
            "delta": delta,
            "step_completed": "14_approved",
            "duration_ms": duration_ms
        }

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _reject(self, reason, step, current_pool_ev=0.0, best_ev=0.0, delta=0.0):
        """Build a standardized rejection result (see 10_delta_selector.py)."""
        return {
            "approved": False, "reason": reason, "recommendation": None,
            "current_pool_ev": current_pool_ev, "best_candidate_ev": best_ev,
            "delta": delta, "step_completed": step
        }

    def _get_cluster_optimization_mode(self, cluster_id: str) -> str:
        """Fetch optimization mode from Redis or fall back to BALANCED."""
        try:
            cached = self.redis.get(f"spot:cluster_mode:{cluster_id}")
            return cached.decode("utf-8") if cached else DEFAULT_PROFILE
        except Exception:
            return DEFAULT_PROFILE

    def _load_global_rankings(self, region: str):
        """Load global ML rankings from Redis (set by Intelligence Layer)."""
        try:
            data = self.redis.get(f"spot:global_rankings:{region}")
            return json.loads(data) if data else None
        except Exception:
            return None

    def _check_pricing_freshness(self, region: str) -> tuple:
        """Check if regional pricing data is < 15 minutes old."""
        from datetime import datetime
        try:
            raw = self.redis.get(f"pricing:last_updated:{region}")
            if not raw:
                return True, 0.0  # Fail-open
            last_updated = datetime.fromisoformat(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            staleness = (datetime.utcnow() - last_updated).total_seconds() / 60
            return staleness <= 15, staleness
        except Exception:
            return True, 0.0  # Fail-open

    def _check_volatility_regime(self, region: str) -> bool:
        """Check if region is in volatile market regime."""
        try:
            val = self.redis.get(f"spot:volatility_regime:{region}")
            return val == b"true"
        except Exception:
            return False

    def _apply_template_filters(self, pools, template_id):
        """Apply node template whitelist/blacklist filters (see 08_template_filter.py)."""
        try:
            data = self.redis.get(f"spot:template:{template_id}")
            if not data:
                return pools
            template = json.loads(data)
            whitelist = template.get("instance_families", [])
            blacklist = set(template.get("blacklisted_pools", []))
            return [
                p for p in pools
                if f"{p['instance_type']}:{p['az']}" not in blacklist
                and (not whitelist or p["instance_type"].split(".")[0] in whitelist)
            ]
        except Exception:
            return pools

    def _apply_karpenter_filters(self, pools, filters):
        """Apply Karpenter NodePool requirement filters (see 08_template_filter.py)."""
        try:
            filtered = []
            for pool in pools:
                if filters.get("architecture") and pool.get("architecture") != filters["architecture"]:
                    continue
                if filters.get("capacity_type") and pool.get("capacity_type") != filters["capacity_type"]:
                    continue
                filtered.append(pool)
            return filtered
        except Exception:
            return pools

    def _emit_metric(self, metric_name: str, cluster_id: str):
        """Emit observability counter to Redis (for monitoring dashboard)."""
        try:
            self.redis.incr(f"spot:metrics:{metric_name}")
            self.redis.expire(f"spot:metrics:{metric_name}", 86400)
            if "rejected" in metric_name:
                category = metric_name.split(".")[-1]
                self.redis.hincrby(f"spot:rejection_counters:{cluster_id}", category, 1)
                self.redis.hincrby(f"spot:rejection_counters:{cluster_id}", "total", 1)
                self.redis.expire(f"spot:rejection_counters:{cluster_id}", 86400)
        except Exception:
            pass
