"""
Decision Engine v3 - Modular Policy Layer for Pool Selection
=============================================================

COMPLETE REWRITE - This file replaces the legacy conflict resolver architecture.

Responsibilities:
1. Evaluate action plans (pool switches) against policy constraints
2. Enforce cooldowns, diversity, workload classification, and risk ceilings
3. Re-score pools using current expected value
4. Apply delta threshold to prevent micro-switches
5. Handle cascade fallback when no valid candidate exists

Architecture:
- Step-based pipeline with early exits
- Integrates with CooldownController, DiversityEnforcer, WorkloadInspector, BlacklistService
- Uses compute_expected_value from backend.core.scoring for all EV calculations
- Supports three optimization profiles: COST_FIRST, BALANCED, NO_DOWNTIME_FIRST

Usage:
    engine = DecisionEngine(redis, db)
    result = engine.evaluate_action_plan(
        cluster_id="prod-cluster",
        current_pool={"instance_type": "m5.large", "az": "us-east-1a"},
        candidate_pools=[...],
        action_type="POOL_SWITCH"
    )

    if result["approved"]:
        # Execute recommendation
        action_executor.execute(result["recommendation"])
    else:
        # Log rejection reason
        logger.info(f"Action blocked: {result['reason']}")
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from redis import Redis
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.core.scoring import compute_expected_value
from backend.core.ev_model import evaluate_candidate_ev, get_dynamic_capacity_failure_probability
from backend.services.cooldown_controller import CooldownController
from backend.services.diversity_enforcer import DiversityEnforcer
from backend.services.workload_inspector import WorkloadInspector, NodeStatus
from backend.services.blacklist_service import BlacklistService


# ============================================================================
# OPTIMIZATION PROFILES
# ============================================================================

OPTIMIZATION_PROFILES = {
    "COST_FIRST": {
        "risk_ceiling": 0.25,              # Accept up to 25% risk
        "delta_threshold": 0.02,           # 2% EV improvement required (lowered from 3%)
        "max_family_ratio": 0.4,           # Max 40% in single family
        "max_az_ratio": 0.5,               # Max 50% in single AZ
        "capacity_freshness_min": 80,      # Capacity data must be <80 min old
        "staleness_penalty": 0.95,         # 5% penalty for stale data
        "volatility_ceiling_adjustment": -0.05  # Lower ceiling by 5% in volatile markets
    },
    "BALANCED": {
        "risk_ceiling": 0.20,              # Accept up to 20% risk
        "delta_threshold": 0.03,           # 3% EV improvement required (lowered from 5%)
        "max_family_ratio": 0.4,
        "max_az_ratio": 0.5,
        "capacity_freshness_min": 80,
        "staleness_penalty": 0.95,
        "volatility_ceiling_adjustment": -0.05
    },
    "NO_DOWNTIME_FIRST": {
        "risk_ceiling": 0.10,              # Accept up to 10% risk
        "delta_threshold": 0.04,           # 4% EV improvement required (lowered from 8%)
        "max_family_ratio": 0.3,           # Max 30% in single family
        "max_az_ratio": 0.4,               # Max 40% in single AZ
        "capacity_freshness_min": 80,
        "staleness_penalty": 0.95,
        "volatility_ceiling_adjustment": -0.05
    }
}

DEFAULT_PROFILE = "BALANCED"

# ============================================================================
# MODEL VERSION CONSTANTS
# ============================================================================

CURRENT_MODEL_VERSION = "6"  # Must match regressor_6.onnx
ITN_BYPASS_ENABLED = True    # Allow ITN (interruption termination notice) cascade


# ============================================================================
# DECISION ENGINE CLASS
# ============================================================================

class DecisionEngine:
    """
    Policy-based decision engine for spot pool optimization.

    Evaluates action plans through a 15-step pipeline:
    1. Check cluster cooldown
    2. Check pool cooldown
    2b. Fetch node classification
    2c. Filter STATELESS_ELIGIBLE nodes
    3. Validate model version
    4. Load optimization mode
    5. Load global rankings
    6. Apply risk ceiling
    7. Apply capacity freshness validation
    8. Apply volatility guard
    9. Re-score all pools
    10. Score current pool
    11. Apply template + Karpenter filters
    12. Apply diversity check
    13. Apply delta threshold
    14. Select best candidate
    15. Check cascade fallback
    """

    def __init__(self, redis: Redis, db: Session):
        self.redis = redis
        self.db = db

        # Initialize sub-services
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
        Evaluate an action plan (pool switch) against policy constraints.

        Args:
            cluster_id: Cluster identifier
            current_pool: Current pool dict with keys: instance_type, az, predicted_savings, risk_probability
            candidate_pools: List of candidate pool dicts
            action_type: Type of action (POOL_SWITCH, SCALE_OUT, etc.)
            optimization_mode: Override optimization mode (COST_FIRST, BALANCED, NO_DOWNTIME_FIRST)
            template_id: Node template ID for filtering
            karpenter_filters: Karpenter constraints
            cluster_node_distribution: Current node distribution for diversity checks
            total_nodes: Current total node count
            is_emergency: Emergency override (e.g., spot termination notice)

        Returns:
            {
                "approved": bool,
                "reason": str,
                "recommendation": Dict or None,
                "current_pool_ev": float,
                "best_candidate_ev": float,
                "delta": float,
                "step_completed": str
            }
        """

        start_time = datetime.utcnow()

        # ====================================================================
        # STEP 1: Check cluster cooldown
        # ====================================================================

        if not is_emergency:
            can_switch, remaining_seconds = self.cooldown.can_switch(cluster_id)

            if not can_switch:
                self._emit_metric("decision.rejected.cooldown", cluster_id)
                return {
                    "approved": False,
                    "reason": f"Cluster cooldown active ({remaining_seconds}s remaining)",
                    "recommendation": None,
                    "current_pool_ev": 0.0,
                    "best_candidate_ev": 0.0,
                    "delta": 0.0,
                    "step_completed": "1_cluster_cooldown"
                }

        # ====================================================================
        # STEP 1b: Check pricing freshness (FIX 5)
        # ====================================================================

        if not is_emergency:
            region = current_pool.get("region", "us-east-1")
            pricing_key = f"pricing:last_updated:{region}"
            try:
                last_updated_raw = self.redis.get(pricing_key)
                if last_updated_raw:
                    last_updated = datetime.fromisoformat(last_updated_raw.decode('utf-8'))
                    staleness_minutes = (datetime.utcnow() - last_updated).total_seconds() / 60

                    if staleness_minutes > 15:
                        self._emit_metric("decision.rejected.pricing_stale", cluster_id)
                        return {
                            "approved": False,
                            "reason": f"Pricing data stale ({staleness_minutes:.0f} min old, max 15 min)",
                            "recommendation": None,
                            "current_pool_ev": 0.0,
                            "best_candidate_ev": 0.0,
                            "delta": 0.0,
                            "step_completed": "1b_pricing_freshness"
                        }
                else:
                    logger.warning(f"No pricing timestamp found for region {region}")
                    # Fail-open: allow execution if no timestamp exists
            except Exception as e:
                logger.error(f"Error checking pricing freshness: {e}")
                # Fail-open: allow execution if check fails

        # ====================================================================
        # STEP 2: Check pool cooldown (remove cooled pools from candidates)
        # ====================================================================

        valid_candidates = []
        for pool in candidate_pools:
            pool_key = f"{pool['instance_type']}:{pool['az']}"
            can_reuse, remaining = self.cooldown.can_reuse_pool(pool_key)

            if can_reuse or (is_emergency and ITN_BYPASS_ENABLED):
                valid_candidates.append(pool)
            else:
                logger.debug(f"Pool {pool_key} in cooldown, skipping ({remaining}s remaining)")

        if not valid_candidates:
            self._emit_metric("decision.rejected.all_pools_cooled", cluster_id)
            return {
                "approved": False,
                "reason": "All candidate pools in cooldown",
                "recommendation": None,
                "current_pool_ev": 0.0,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "2_pool_cooldown"
            }

        # ====================================================================
        # STEP 2b: Fetch node classification
        # ====================================================================

        classification = self.workload.get_cached_classification(cluster_id)

        if not classification:
            logger.warning(f"No node classification found for cluster {cluster_id}")
            self._emit_metric("decision.rejected.no_classification", cluster_id)
            return {
                "approved": False,
                "reason": "Node classification unavailable (WorkloadInspector scan required)",
                "recommendation": None,
                "current_pool_ev": 0.0,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "2b_node_classification"
            }

        # ====================================================================
        # STEP 2c: Filter STATELESS_ELIGIBLE nodes
        # ====================================================================

        stateless_nodes = [
            node_name for node_name, status in classification.items()
            if status == NodeStatus.STATELESS_ELIGIBLE
        ]

        if not stateless_nodes:
            self._emit_metric("decision.rejected.no_stateless_nodes", cluster_id)
            return {
                "approved": False,
                "reason": "No STATELESS_ELIGIBLE nodes found (all nodes protected)",
                "recommendation": None,
                "current_pool_ev": 0.0,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "2c_stateless_filter"
            }

        logger.info(
            f"Cluster {cluster_id}: {len(stateless_nodes)}/{len(classification)} nodes eligible"
        )

        # ====================================================================
        # STEP 3: Validate model version
        # ====================================================================

        for pool in valid_candidates:
            model_version = pool.get("model_version", "unknown")

            if model_version != CURRENT_MODEL_VERSION:
                if not ITN_BYPASS_ENABLED:
                    logger.warning(
                        f"Pool {pool['instance_type']}:{pool['az']} uses model v{model_version}, "
                        f"expected v{CURRENT_MODEL_VERSION}"
                    )
                    self._emit_metric("decision.model_version_mismatch", cluster_id)

        # ====================================================================
        # STEP 4: Load optimization mode
        # ====================================================================

        if not optimization_mode:
            # Fetch from cluster settings
            optimization_mode = self._get_cluster_optimization_mode(cluster_id)

        profile = OPTIMIZATION_PROFILES.get(optimization_mode, OPTIMIZATION_PROFILES[DEFAULT_PROFILE])

        logger.info(f"Using optimization profile: {optimization_mode}")

        # ====================================================================
        # STEP 5: Load global rankings from Redis
        # ====================================================================

        region = current_pool.get("region", "us-east-1")  # Default region
        global_rankings = self._load_global_rankings(region)

        if not global_rankings:
            logger.warning(f"No global rankings found for region {region}")
            self._emit_metric("decision.rejected.no_rankings", cluster_id)
            return {
                "approved": False,
                "reason": "Global rankings unavailable (Intelligence Layer required)",
                "recommendation": None,
                "current_pool_ev": 0.0,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "5_global_rankings"
            }

        # ====================================================================
        # STEP 6: Apply THREE-LAYER RISK CEILING (Task 5.1)
        # Layer 1: Profile ceiling (from optimization mode)
        # Layer 2: Volatility ceiling adjustment
        # Layer 3: Trust-phase override (progressive trust)
        # ====================================================================

        # Layer 1: Profile ceiling
        risk_ceiling = profile["risk_ceiling"]

        # Layer 2: Volatility ceiling adjustment
        is_volatile = self._check_volatility_regime(region)

        if is_volatile:
            adjustment = profile["volatility_ceiling_adjustment"]
            risk_ceiling += adjustment
            logger.warning(
                f"Volatile market detected, adjusting risk ceiling to {risk_ceiling:.2f}"
            )

        # Layer 3: Trust-phase override (use most restrictive)
        try:
            from backend.services.optimizer_coordinator import OptimizerCoordinator
            coordinator = OptimizerCoordinator(self.db, self.redis)
            trust = coordinator.get_cluster_trust_phase(cluster_id)
            trust_ceiling = trust.get("risk_ceiling_override")
            if trust_ceiling is not None:
                risk_ceiling = min(risk_ceiling, trust_ceiling)
                logger.info(
                    f"Trust phase {trust['phase']} ceiling: {trust_ceiling:.2f}, "
                    f"effective ceiling: {risk_ceiling:.2f}"
                )
        except Exception as e:
            logger.warning(f"Trust-phase ceiling check failed: {e}")

        valid_candidates = [
            pool for pool in valid_candidates
            if pool.get("risk_probability", 1.0) <= risk_ceiling
        ]

        if not valid_candidates:
            self._emit_metric("decision.rejected.risk_ceiling", cluster_id)
            return {
                "approved": False,
                "reason": f"All candidates exceed risk ceiling ({risk_ceiling:.2%})",
                "recommendation": None,
                "current_pool_ev": 0.0,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "6_risk_ceiling"
            }

        # ====================================================================
        # STEP 7: Apply capacity freshness validation
        # ====================================================================

        freshness_threshold_min = profile["capacity_freshness_min"]
        staleness_penalty = profile["staleness_penalty"]

        for pool in valid_candidates:
            capacity_age_min = pool.get("capacity_age_minutes", 0)

            if capacity_age_min > freshness_threshold_min:
                # Apply staleness penalty to predicted_savings
                original_savings = pool.get("predicted_savings", 0.0)
                pool["predicted_savings"] = original_savings * staleness_penalty
                pool["staleness_penalty_applied"] = True

                logger.debug(
                    f"Stale capacity data for {pool['instance_type']}:{pool['az']} "
                    f"({capacity_age_min} min old), applying {staleness_penalty:.2%} penalty"
                )

        # ====================================================================
        # STEP 8: Apply volatility guard (already applied in Step 6)
        # ====================================================================

        # Risk ceiling already adjusted in Step 6
        pass

        # ====================================================================
        # STEP 9: Re-score all pools using evaluate_candidate_ev() (Task 3.2)
        # Replaces simple savings × (1-risk) with full economic EV model
        # ====================================================================

        ev_eligible_candidates = []
        for pool in valid_candidates:
            predicted_savings = pool.get("predicted_savings", 0.0)
            risk_probability = pool.get("risk_probability", 0.0)
            normalized_volatility = pool.get("normalized_volatility", 0.0)
            pool_id = f"{pool.get('instance_type', '')}:{pool.get('az', '')}"

            try:
                # Use dynamic capacity failure probability from Redis (Task 3.1)
                cap_fail_prob = get_dynamic_capacity_failure_probability(
                    self.redis, pool_id, region
                )

                ev_breakdown = evaluate_candidate_ev(
                    savings=predicted_savings,
                    final_risk=risk_probability,
                    normalized_volatility=normalized_volatility,
                    capacity_failure_probability=cap_fail_prob,
                    downtime_cost_per_hour=100.0,
                    risk_horizon_hours=2.0,
                    recovery_time_hours=0.5,
                )

                if not ev_breakdown["is_eligible"]:
                    # Task 7.1: rejection counter will be added later
                    logger.debug(f"Pool {pool_id} rejected by EV model: ev={ev_breakdown['ev']:.4f}")
                    continue

                pool["expected_value"] = ev_breakdown["ev"]
                pool["ev_breakdown"] = ev_breakdown
                ev_eligible_candidates.append(pool)
            except Exception as e:
                logger.error(f"Error computing EV for pool {pool}: {e}")
                pool["expected_value"] = 0.0

        valid_candidates = ev_eligible_candidates

        # ====================================================================
        # STEP 10: Score current pool
        # ====================================================================

        current_savings = current_pool.get("predicted_savings", 0.0)
        current_risk = current_pool.get("risk_probability", 0.0)

        try:
            current_pool_ev = compute_expected_value(
                predicted_savings=current_savings,
                risk_probability=current_risk
            )
        except ValueError as e:
            logger.error(f"Error computing EV for current pool: {e}")
            current_pool_ev = 0.0

        logger.info(f"Current pool EV: {current_pool_ev:.4f}")

        # ====================================================================
        # STEP 11: Apply template + Karpenter filters
        # ====================================================================

        if template_id:
            valid_candidates = self._apply_template_filters(valid_candidates, template_id)

        if karpenter_filters:
            valid_candidates = self._apply_karpenter_filters(valid_candidates, karpenter_filters)

        if not valid_candidates:
            self._emit_metric("decision.rejected.template_filters", cluster_id)
            return {
                "approved": False,
                "reason": "No candidates pass template/Karpenter filters",
                "recommendation": None,
                "current_pool_ev": current_pool_ev,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "11_template_filters"
            }

        # ====================================================================
        # STEP 12: Apply diversity check
        # ====================================================================

        if cluster_node_distribution and not (is_emergency and ITN_BYPASS_ENABLED):
            diversity_passed_candidates = []

            for pool in valid_candidates:
                passes, reason = self.diversity.check_candidate(
                    candidate_pool=pool,
                    cluster_node_distribution=cluster_node_distribution,
                    total_nodes=total_nodes,
                    max_family_ratio=profile["max_family_ratio"],
                    max_az_ratio=profile["max_az_ratio"]
                )

                if passes:
                    diversity_passed_candidates.append(pool)
                else:
                    logger.debug(f"Diversity check failed for {pool['instance_type']}: {reason}")

            valid_candidates = diversity_passed_candidates

        if not valid_candidates:
            # Deadlock protection: hold current pool if safe
            if current_pool_ev >= 0.5:  # Arbitrary safety threshold
                logger.warning("No diversity-compliant candidates, holding current pool")
                self._emit_metric("decision.deadlock_hold", cluster_id)
                return {
                    "approved": False,
                    "reason": "No diversity-compliant candidates (holding safe current pool)",
                    "recommendation": None,
                    "current_pool_ev": current_pool_ev,
                    "best_candidate_ev": 0.0,
                    "delta": 0.0,
                    "step_completed": "12_diversity_deadlock"
                }

            self._emit_metric("decision.rejected.diversity", cluster_id)
            return {
                "approved": False,
                "reason": "No candidates pass diversity constraints",
                "recommendation": None,
                "current_pool_ev": current_pool_ev,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "12_diversity"
            }

        # ====================================================================
        # STEP 13: Apply delta threshold
        # ====================================================================

        # Sort by EV descending
        valid_candidates.sort(key=lambda p: p.get("expected_value", 0.0), reverse=True)

        best_candidate = valid_candidates[0] if valid_candidates else None

        if not best_candidate:
            self._emit_metric("decision.rejected.no_candidates", cluster_id)
            return {
                "approved": False,
                "reason": "No valid candidates after all filters",
                "recommendation": None,
                "current_pool_ev": current_pool_ev,
                "best_candidate_ev": 0.0,
                "delta": 0.0,
                "step_completed": "13_no_candidates"
            }

        best_candidate_ev = best_candidate.get("expected_value", 0.0)
        delta = best_candidate_ev - current_pool_ev
        delta_threshold = profile["delta_threshold"]

        logger.info(
            f"Best candidate: {best_candidate['instance_type']}:{best_candidate['az']} "
            f"(EV: {best_candidate_ev:.4f}, delta: {delta:.4f})"
        )

        if delta < delta_threshold:
            self._emit_metric("decision.rejected.delta_threshold", cluster_id)
            return {
                "approved": False,
                "reason": f"Delta {delta:.4f} below threshold {delta_threshold:.4f}",
                "recommendation": None,
                "current_pool_ev": current_pool_ev,
                "best_candidate_ev": best_candidate_ev,
                "delta": delta,
                "step_completed": "13_delta_threshold"
            }

        # ====================================================================
        # STEP 14: Select best candidate
        # ====================================================================

        self._emit_metric("decision.approved", cluster_id)

        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        logger.info(
            f"DECISION APPROVED: Switch to {best_candidate['instance_type']}:{best_candidate['az']} "
            f"(EV improvement: {delta:.4f}, duration: {duration_ms:.0f}ms)"
        )

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

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_cluster_optimization_mode(self, cluster_id: str) -> str:
        """Fetch optimization mode from cluster settings (DB or Redis cache)."""
        try:
            cache_key = f"spot:cluster_mode:{cluster_id}"
            cached_mode = self.redis.get(cache_key)

            if cached_mode:
                return cached_mode.decode('utf-8')

            # Fallback: query database
            # cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            # if cluster and cluster.optimization_mode:
            #     self.redis.setex(cache_key, 300, cluster.optimization_mode)
            #     return cluster.optimization_mode

            return DEFAULT_PROFILE

        except Exception as e:
            logger.error(f"Error fetching optimization mode: {e}")
            return DEFAULT_PROFILE

    def _load_global_rankings(self, region: str) -> Optional[Dict]:
        """Load global rankings from Redis (Intelligence Layer output).

        Issue #6: On cache miss, triggers a synchronous rebuild via the pool
        ranking pipeline instead of waiting for the next Celery beat cycle.
        """
        try:
            cache_key = f"spot:global_rankings:{region}"
            data = self.redis.get(cache_key)

            if data:
                return json.loads(data)

            # Issue #6: Cache miss — attempt synchronous rebuild
            logger.warning(
                f"Global pool rankings cache miss for region {region}, "
                f"triggering synchronous rebuild"
            )
            try:
                from backend.services.pool_ranking_service import PoolRankingService
                ranking_svc = PoolRankingService(self.redis, self.db)
                ranking_svc.refresh_global_rankings(region)

                # Retry read after rebuild
                data = self.redis.get(cache_key)
                if data:
                    logger.info(f"Global rankings rebuilt successfully for {region}")
                    return json.loads(data)
            except Exception as rebuild_err:
                logger.error(f"Synchronous rankings rebuild failed for {region}: {rebuild_err}")

            return None

        except Exception as e:
            logger.error(f"Error loading global rankings: {e}")
            return None

    def _check_volatility_regime(self, region: str) -> bool:
        """Check if region is in volatile market regime."""
        try:
            cache_key = f"spot:volatility_regime:{region}"
            is_volatile = self.redis.get(cache_key)

            return is_volatile == b"true" if is_volatile else False

        except Exception as e:
            logger.error(f"Error checking volatility regime: {e}")
            return False

    def _apply_template_filters(self, pools: List[Dict], template_id: str) -> List[Dict]:
        """Apply node template filters (instance family whitelist/blacklist)."""
        try:
            # Fetch template from DB or cache
            cache_key = f"spot:template:{template_id}"
            template_data = self.redis.get(cache_key)

            if not template_data:
                logger.warning(f"Template {template_id} not found, skipping filter")
                return pools

            template = json.loads(template_data)

            whitelist = template.get("instance_families", [])
            blacklist = template.get("blacklisted_pools", [])

            filtered = []

            for pool in pools:
                instance_type = pool["instance_type"]
                family = instance_type.split('.')[0]
                pool_key = f"{instance_type}:{pool['az']}"

                # Check blacklist
                if pool_key in blacklist:
                    logger.debug(f"Pool {pool_key} in template blacklist")
                    continue

                # Check whitelist
                if whitelist and family not in whitelist:
                    logger.debug(f"Pool {pool_key} family not in whitelist")
                    continue

                filtered.append(pool)

            return filtered

        except Exception as e:
            logger.error(f"Error applying template filters: {e}")
            return pools

    def _apply_karpenter_filters(self, pools: List[Dict], filters: Dict) -> List[Dict]:
        """Apply Karpenter constraints (architecture, capacity type, etc.)."""
        try:
            filtered = []

            for pool in pools:
                # Architecture filter
                required_arch = filters.get("architecture")
                if required_arch and pool.get("architecture") != required_arch:
                    continue

                # Capacity type filter
                required_capacity = filters.get("capacity_type")
                if required_capacity and pool.get("capacity_type") != required_capacity:
                    continue

                filtered.append(pool)

            return filtered

        except Exception as e:
            logger.error(f"Error applying Karpenter filters: {e}")
            return pools

    def _emit_metric(self, metric_name: str, cluster_id: str):
        """Emit observability metric to Redis or monitoring system."""
        try:
            metric_key = f"spot:metrics:{metric_name}"
            self.redis.incr(metric_key)
            self.redis.expire(metric_key, 86400)  # 24-hour TTL

            # ── Task 7.1: Per-cluster rejection counters ──────────
            if "rejected" in metric_name:
                # Extract rejection category from metric name
                # e.g., "decision.rejected.cooldown" -> "cooldown"
                parts = metric_name.split(".")
                category = parts[-1] if len(parts) > 2 else "unknown"

                counter_key = f"spot:rejection_counters:{cluster_id}"
                self.redis.hincrby(counter_key, category, 1)
                self.redis.hincrby(counter_key, "total", 1)
                self.redis.expire(counter_key, 86400)  # 24-hour TTL

            # Also log to structured logger
            logger.debug(f"Metric emitted: {metric_name} (cluster: {cluster_id})")

        except Exception as e:
            logger.error(f"Error emitting metric: {e}")

    def get_rejection_counters(self, cluster_id: str) -> dict:
        """
        Task 7.1: Get rejection counters for a cluster.
        Returns breakdown of why decisions were rejected.
        """
        try:
            counter_key = f"spot:rejection_counters:{cluster_id}"
            raw = self.redis.hgetall(counter_key)
            return {k.decode(): int(v) for k, v in raw.items()} if raw else {}
        except Exception as e:
            logger.error(f"Error getting rejection counters: {e}")
            return {}

    def rank_for_node(self, cluster_id: str, node_info: dict, region: str) -> list:
        """
        Rank pools for a specific node using the global pool cache.

        Steps:
        1. Circuit breaker HALT check → return []
        2. Degraded region check → return []
        3. Load global pool cache from Redis
        4. Derive floor from node_info
        5. _apply_filters — remove blacklisted, non-compliant, price-shocked pools
        6. _apply_double_gate — keep only cheaper AND safer pools
        7. _relax_with_trade_off — if empty, allow ≤trade_off_pct% more expensive but strictly safer
        8. _relax_with_tier_expansion — expand tier 1→2→3→4
        """
        import json as _json
        from backend.core.redis_client import (
            get_redis_client,
            key_global_pool_rankings,
            key_market_view_cache,
            key_degraded_region,
        )
        from backend.core.config import PRICE_SPIKE_FACTOR

        _node_label = node_info.get('instance_id', node_info.get('instance_type', '?'))
        logger.info(
            f"[DE.rank_for_node] START | node={_node_label} cluster={cluster_id} region={region} "
            f"spot_price={node_info.get('spot_price')} risk_tier={node_info.get('risk_tier')} "
            f"instance_type={node_info.get('instance_type')} az={node_info.get('az')}"
        )

        # Step 1: Circuit breaker HALT check
        try:
            from backend.services.circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(self.redis)
            state = cb.get_state(cluster_id)
            if state == "HALT":
                logger.warning(f"[DE.rank_for_node] GATE1_FAIL: Cluster {cluster_id} circuit breaker HALT — returning []")
                return []
            logger.debug(f"[DE.rank_for_node] GATE1_PASS: CB state={state}")
        except Exception as cb_err:
            logger.debug(f"[DE.rank_for_node] GATE1_WARN: Circuit breaker check error: {cb_err}")

        # Step 2: Degraded region check
        try:
            r = get_redis_client()
            if r.exists(key_degraded_region(region)):
                logger.warning(f"[DE.rank_for_node] GATE2_FAIL: Region {region} is degraded — returning []")
                return []
            logger.debug(f"[DE.rank_for_node] GATE2_PASS: Region {region} not degraded")
        except Exception:
            r = get_redis_client()

        # Step 3: Load global pool cache
        # Try market_view_cache first (written by cache_builder with 500+ pools),
        # then fall back to global_pool_rankings (written by pool_ranking_service with ~42 pools)
        try:
            mv_key = key_market_view_cache(region)
            raw = r.get(mv_key)
            cache_source = "market_view_cache"
            if not raw:
                logger.warning(
                    f"[DE.rank_for_node] GATE3_WARN: market_view_cache:{region} empty — "
                    f"falling back to global_pool_rankings:{region}"
                )
                fallback_key = key_global_pool_rankings(region)
                raw = r.get(fallback_key)
                cache_source = "global_pool_rankings"
            if not raw:
                logger.warning(
                    f"[DE.rank_for_node] GATE3_FAIL: No pool cache found for region {region} "
                    f"(checked market_view_cache and global_pool_rankings). "
                    f"Run cache_builder Celery task to populate."
                )
                return []
            payload = _json.loads(raw)
            all_pools = payload.get('data', [])
            logger.info(
                f"[DE.rank_for_node] GATE3_PASS: Loaded {len(all_pools)} pools from "
                f"{cache_source}:{region}"
            )
        except Exception as cache_err:
            logger.error(f"[DE.rank_for_node] GATE3_FAIL: Cache load error: {cache_err}")
            return []

        # Step 4: Derive floor from node_info — use resource_profile gates if provided
        resource_profile = node_info.get('resource_profile', {})
        min_vcpu = resource_profile.get('min_vcpu_required', 0)
        min_memory_gb = resource_profile.get('min_memory_required', 0.0)
        required_arch = resource_profile.get('architecture')  # e.g. 'amd64', 'arm64'
        # BUGFIX: if price is 0 (new node or price not yet fetched), skip price gate entirely
        current_price = float(node_info.get('spot_price', 0) or 0)
        current_risk_tier = int(node_info.get('risk_tier', 4) or 4)

        logger.info(
            f"[DE.rank_for_node] GATE4: node_info gates: min_vcpu={min_vcpu} min_memory={min_memory_gb} "
            f"required_arch={required_arch} current_price={current_price} current_risk_tier={current_risk_tier}"
        )

        # Rejection audit counters (Task 2.6)
        _audit = {
            "raw_pool_count":          len(all_pools),
            "blacklisted":             0,
            "too_small_vcpu":          0,
            "too_small_memory":        0,
            "architecture_incompatible": 0,
        }

        # Step 5: Apply blacklist / price-shock filter
        pools_after_blacklist = self._apply_filters(all_pools, node_info, cluster_id)
        _audit["blacklisted"] = len(all_pools) - len(pools_after_blacklist)
        pools = pools_after_blacklist
        logger.info(
            f"[DE.rank_for_node] GATE5: After blacklist filter: {len(pools)}/{len(all_pools)} pools "
            f"(removed {_audit['blacklisted']} blacklisted)"
        )

        # Resource profile gates (Part 2 per-node hard gates from changes.md)
        if min_vcpu > 0:
            before = len(pools)
            pools = [p for p in pools if p.get('vcpu', 0) >= min_vcpu]
            _audit["too_small_vcpu"] = before - len(pools)
            logger.info(f"[DE.rank_for_node] GATE5b: vcpu>={min_vcpu}: {len(pools)} remain (removed {_audit['too_small_vcpu']})")
        if min_memory_gb > 0:
            before = len(pools)
            pools = [p for p in pools if p.get('memory_gb', 0.0) >= min_memory_gb]
            _audit["too_small_memory"] = before - len(pools)
            logger.info(f"[DE.rank_for_node] GATE5c: memory>={min_memory_gb}: {len(pools)} remain (removed {_audit['too_small_memory']})")
        if required_arch:
            before = len(pools)
            pools = [p for p in pools if p.get('architecture', 'amd64') == required_arch]
            _audit["architecture_incompatible"] = before - len(pools)
            logger.info(f"[DE.rank_for_node] GATE5d: arch={required_arch}: {len(pools)} remain (removed {_audit['architecture_incompatible']})")

        # Step 6: Apply double gate — must be cheaper AND safer (lower tier)
        # BUGFIX: if current_price == 0, skip price comparison (we don't know current price)
        gated = self._apply_double_gate(pools, current_price, current_risk_tier)
        logger.info(
            f"[DE.rank_for_node] GATE6 (double gate cheaper+safer): {len(gated)}/{len(pools)} pools passed "
            f"(current_price={current_price}, current_risk_tier={current_risk_tier})"
        )

        # Step 7: Relax with trade-off if empty
        if not gated:
            trade_off_pct = float(node_info.get('trade_off_pct', 20.0))
            gated = self._relax_with_trade_off(pools, current_price, current_risk_tier, trade_off_pct)
            logger.info(
                f"[DE.rank_for_node] GATE7 (trade-off relax ±{trade_off_pct}%): "
                f"{len(gated)} pools after relaxation"
            )

        # Step 8: Expand tier if still empty
        if not gated:
            logger.warning(
                f"[DE.rank_for_node] GATE8: Double-gate + trade-off both empty. "
                f"Falling back to tier expansion from all {len(all_pools)} pools"
            )
            gated = self._relax_with_tier_expansion(all_pools, current_risk_tier)
            logger.info(f"[DE.rank_for_node] GATE8 (tier expansion): {len(gated)} pools after expansion")

        # Final summary
        logger.info(
            f"[DE.rank_for_node] RESULT | node={_node_label} cluster={cluster_id} | "
            f"raw={_audit['raw_pool_count']} eligible={len(gated)} | "
            f"blacklisted={_audit['blacklisted']} "
            f"too_small_vcpu={_audit['too_small_vcpu']} "
            f"too_small_memory={_audit['too_small_memory']} "
            f"arch_incompatible={_audit['architecture_incompatible']}"
        )
        if gated:
            top = gated[0]
            logger.info(
                f"[DE.rank_for_node] TOP_POOL: {top.get('instance_type')}:{top.get('az')} "
                f"spot=${top.get('spot_price')} risk_tier={top.get('risk_tier')} "
                f"savings={top.get('savings_pct')}%"
            )
        else:
            logger.warning(
                f"[DE.rank_for_node] NO_ALTERNATIVES: All gates eliminated all pools. "
                f"Check: (1) pool cache populated? (2) current_price={current_price} vs pool prices "
                f"(3) current_risk_tier={current_risk_tier}"
            )

        # Cache pool audit in Redis for /pool-audit API (Task 4.3)
        try:
            import json as _j
            r.setex(
                f"pool_audit:{cluster_id}:{_node_label}",
                300,
                _j.dumps({
                    "raw_pool_count": _audit["raw_pool_count"],
                    "eligible_count": len(gated),
                    "rejection_reasons": {k: v for k, v in _audit.items() if k != "raw_pool_count"},
                    "computed_at": __import__('datetime').datetime.utcnow().isoformat(),
                })
            )
        except Exception:
            pass

        return gated

    def _apply_filters(self, pools: list, node_info: dict, cluster_id: str) -> list:
        """Remove blacklisted, price-shocked pools."""
        from backend.core.redis_client import get_redis_client, key_blacklist_global
        from backend.core.config import PRICE_SPIKE_FACTOR
        try:
            r = get_redis_client()
            result = []
            for pool in pools:
                pool_key = f"{pool['instance_type']}:{pool['az']}"
                # Blacklist check
                if r.exists(key_blacklist_global(pool_key)):
                    continue
                # Price shock check — skip if pool price > PRICE_SPIKE_FACTOR * avg
                # (simplified: use current_price as proxy for avg)
                result.append(pool)
            return result
        except Exception:
            return pools

    def _apply_double_gate(self, pools: list, current_price: float, current_risk_tier: int) -> list:
        """
        Keep pools that are both cheaper AND have lower or equal risk tier.

        BUGFIX: if current_price == 0 (node price unknown or pre-launch), skip the price
        comparison entirely and only gate on risk tier. This prevents all pools from being
        eliminated when the node's spot_price hasn't been fetched yet.
        """
        if current_price <= 0:
            # Price unknown — only filter on risk tier (never eliminate all pools)
            logger.debug(
                f"[DE._apply_double_gate] current_price=0, skipping price gate. "
                f"Only applying risk_tier<={current_risk_tier} gate."
            )
            return [p for p in pools if p.get('risk_tier', 4) <= current_risk_tier]
        return [
            p for p in pools
            if p.get('spot_price', 9999) < current_price
            and p.get('risk_tier', 4) <= current_risk_tier
        ]

    def _relax_with_trade_off(self, pools: list, current_price: float,
                               current_risk_tier: int, trade_off_pct: float) -> list:
        """Allow up to trade_off_pct% more expensive but strictly safer (lower tier).
        If current_price==0, include all pools at a strictly lower risk tier.
        """
        if current_price <= 0:
            return [p for p in pools if p.get('risk_tier', 4) < current_risk_tier]
        max_price = current_price * (1 + trade_off_pct / 100.0)
        return [
            p for p in pools
            if p.get('spot_price', 9999) <= max_price
            and p.get('risk_tier', 4) < current_risk_tier
        ]

    def _relax_with_tier_expansion(self, all_pools: list, current_tier: int) -> list:
        """Progressively expand from current tier outward: tier+1 → tier+2 → any."""
        for expand_by in range(1, 5):
            candidate_tier = current_tier + expand_by
            candidates = [p for p in all_pools if p.get('risk_tier', 4) <= candidate_tier]
            if candidates:
                return sorted(candidates, key=lambda p: p.get('spot_price', 9999))
        return sorted(all_pools, key=lambda p: p.get('spot_price', 9999))

    # ── Task 2.5 — ML Scoring Tiers ──────────────────────────────────────────

    def get_ml_score(self, pool: dict, category_mapping: dict) -> tuple:
        """
        Return (ml_score, tier) for a pool using tier1/tier2/tier3 logic.

        Tier 1: ONNX model trained on these families — direct inference, penalty 1.0
        Tier 2: proxy family + penalty (0.85–0.90)
        Tier 3: size-class average × 0.75

        Never raises. Never drops a pool for unknown family.
        Returns (score, tier) where score ∈ [0, 1].
        """
        import re

        instance_type = pool.get('instance_type', '')
        # Extract family: m7i.large → m7i, t3.medium → t3
        match = re.match(r'^([a-z][a-z0-9]+)', instance_type)
        family = match.group(1) if match else ''

        tier1 = category_mapping.get('tier1', [])
        tier2 = category_mapping.get('tier2', {})
        tier3_penalty = float(category_mapping.get('tier3_penalty', 0.75))

        raw_score = pool.get('ml_score', 0.5)  # pre-computed or default 0.5

        if family in tier1:
            # Direct ONNX inference — use pre-computed ml_score as-is
            return min(1.0, max(0.0, raw_score)), 1

        elif family in tier2:
            penalty = float(tier2[family].get('penalty', 0.90))
            # Use proxy family's score if available, else raw_score
            proxy_score = pool.get('proxy_ml_score', raw_score)
            return min(1.0, max(0.0, proxy_score * penalty)), 2

        else:
            # Tier 3: size-class average with 0.75 penalty
            size_class_avg = pool.get('size_class_avg_ml_score', 0.5)
            return min(1.0, max(0.0, size_class_avg * tier3_penalty)), 3

    # ── Task 3.1 + 3.2 — Weighted Scoring Formula ────────────────────────────

    # Profile weight table: {W_savings, W_risk, W_ml}
    _PROFILE_WEIGHTS = {
        'COST_FIRST':  {'savings': 0.60, 'risk': 0.20, 'ml': 0.20},
        'BALANCED':    {'savings': 0.40, 'risk': 0.40, 'ml': 0.20},
        'NO_DOWNTIME': {'savings': 0.20, 'risk': 0.60, 'ml': 0.20},
    }

    def score_and_rank_pools(
        self,
        eligible_pools: list,
        profile: str = 'BALANCED',
        source_od_price: float = 0.0,
        category_mapping: dict = None,
        redis=None,
        cluster_pool_counts: dict = None,
        max_single_pool_pct: float = 0.40,
    ) -> list:
        """
        Apply weighted scoring formula and return pools sorted descending by final_score.

        Pillars 3 + 4 + Dry Run Gate:
        - savings_score        = intrinsic savings (pool OD vs spot) / 0.70 cap
        - safety_score         = 1 - (az_interruption_rate / 25)
        - ml_score             = ONNX / proxy / tier3 with confidence penalty
        - soft_penalty         = 0.85 if pool has recent launch failures
        - reputation_mult      = 0.5–1.2 from pool reputation history (Pillar 3)
        - capacity_boost       = 1.05 if dry_run:pass, 0 (eliminate) if dry_run:fail, 1.0 unverified
        - portfolio_penalty    = concentration penalty when pool already holds >max_single_pool_pct (Pillar 4)
        - momentum_bonus       = ±0.02–0.05 based on recent uptime history (Pillar 4)
        - final_score          = (W_s×savings_score + W_r×safety_score + W_ml×ml_score)
                                 × soft_penalty × reputation_mult × capacity_boost
                                 × (1 - portfolio_penalty) + momentum_bonus

        cluster_pool_counts: dict of {pool_key: node_count} — current cluster node distribution.
                             Pass this to enable portfolio concentration penalty.

        Both intrinsic_savings_pct (for ranking) and customer_savings_pct (for UI) are
        attached to each pool dict.
        """
        if category_mapping is None:
            category_mapping = {}

        # Get Redis client for dry run cache lookups
        _redis = redis or self.redis
        if _redis is None:
            try:
                from backend.core.redis_client import get_redis_client as _grc
                _redis = _grc()
            except Exception:
                _redis = None

        weights = self._PROFILE_WEIGHTS.get(profile, self._PROFILE_WEIGHTS['BALANCED'])
        W_s = weights['savings']
        W_r = weights['risk']
        W_ml = weights['ml']

        scored = []
        eliminated_capacity_fail = 0
        for pool in eligible_pools:
            spot_price = float(pool.get('spot_price', 0.0) or 0.0)
            od_price = float(pool.get('od_price', 0.0) or 0.0)
            az_irr = float(pool.get('az_interruption_rate', pool.get('interruption_rate_pct', 25.0)) or 25.0)

            # Task 3.2: intrinsic savings (for ranking)
            if od_price > 0:
                intrinsic_savings_pct = (od_price - spot_price) / od_price
            else:
                intrinsic_savings_pct = 0.0

            # Task 3.2: customer savings (for UI display — vs source OD node)
            if source_od_price > 0:
                customer_savings_pct = (source_od_price - spot_price) / source_od_price
            else:
                customer_savings_pct = intrinsic_savings_pct

            # Step 1: Absolute normalization
            savings_score = max(0.0, min(intrinsic_savings_pct / 0.70, 1.0))
            safety_score = max(0.0, 1.0 - (az_irr / 25.0))
            ml_raw, _tier = self.get_ml_score(pool, category_mapping)
            ml_score = min(1.0, max(0.0, ml_raw))

            # Step 2: Soft penalty for pools with recent launch failures
            recent_failures = int(pool.get('recent_failure_count', 0) or 0)
            soft_penalty = 0.85 if recent_failures > 0 else 1.0

            # Step 3: Dry run capacity boost / elimination
            instance_type = pool.get('instance_type', '')
            az = pool.get('az', '')
            capacity_status = 'unverified'
            capacity_boost = 1.0
            if _redis and instance_type and az:
                try:
                    pool_key = f"{instance_type}:{az}"
                    dr_cached = _redis.get(f"dry_run:{pool_key}")
                    if dr_cached:
                        dr_val = dr_cached.decode() if isinstance(dr_cached, bytes) else dr_cached
                        if dr_val == 'pass':
                            capacity_status = 'verified'
                            capacity_boost = 1.05  # Capacity confirmed — float to top
                        elif dr_val == 'fail':
                            # Capacity unavailable — eliminate from scoring
                            eliminated_capacity_fail += 1
                            pool = dict(pool)
                            pool['capacity_status'] = 'unavailable'
                            pool['final_score'] = 0.0
                            continue
                except Exception:
                    pass

            # Step 4: Pillar 3 — Pool reputation multiplier
            reputation_mult = 1.0
            avg_uptime = None
            pool_key_rep = f"{instance_type}:{az}"
            if _redis:
                try:
                    from backend.services.pool_ranking_service import get_pool_reputation
                    rep = get_pool_reputation(pool_key_rep, redis_client=_redis)
                    reputation_mult = rep.get("reputation_multiplier", 1.0)
                    avg_uptime = rep.get("avg_uptime_hours")
                except Exception:
                    pass

            # Step 5: Pillar 4 — Portfolio concentration penalty
            portfolio_penalty = 0.0
            total_nodes = sum(cluster_pool_counts.values()) if cluster_pool_counts else 0
            if cluster_pool_counts and total_nodes > 0:
                pool_node_count = cluster_pool_counts.get(pool_key_rep, 0)
                concentration = pool_node_count / total_nodes
                if concentration > max_single_pool_pct:
                    portfolio_penalty = (concentration - max_single_pool_pct) * 2.0
                    portfolio_penalty = min(portfolio_penalty, 0.80)  # cap at 80% penalty

            # Step 6: Pillar 4 — Momentum bonus from recent uptime
            momentum_bonus = 0.0
            if avg_uptime is not None:
                if avg_uptime > 168:    # 7 days without interruption
                    momentum_bonus = 0.05
                elif avg_uptime > 72:   # 3 days stable
                    momentum_bonus = 0.02
                elif avg_uptime < 2:    # interrupted within 2 hours recently
                    momentum_bonus = -0.10

            # Step 7: Final score assembly
            raw_score = (W_s * savings_score) + (W_r * safety_score) + (W_ml * ml_score)
            final_score = (
                raw_score * soft_penalty * reputation_mult * capacity_boost
                * (1.0 - portfolio_penalty)
                + momentum_bonus
            )
            final_score = max(0.0, final_score)

            pool = dict(pool)
            pool['intrinsic_savings_pct'] = round(intrinsic_savings_pct, 4)
            pool['customer_savings_pct'] = round(customer_savings_pct, 4)
            pool['savings_score'] = round(savings_score, 4)
            pool['safety_score'] = round(safety_score, 4)
            pool['ml_score_final'] = round(ml_score, 4)
            pool['ml_tier'] = _tier
            pool['soft_penalty_applied'] = soft_penalty < 1.0
            pool['capacity_status'] = capacity_status
            pool['capacity_boost'] = capacity_boost
            pool['reputation_multiplier'] = round(reputation_mult, 4)
            pool['portfolio_penalty'] = round(portfolio_penalty, 4)
            pool['momentum_bonus'] = round(momentum_bonus, 4)
            pool['final_score'] = round(final_score, 4)
            pool['scoring_profile'] = profile
            scored.append(pool)

        if eliminated_capacity_fail > 0:
            logger.info(
                f"[score_and_rank_pools] Eliminated {eliminated_capacity_fail} pools "
                f"with confirmed capacity unavailability (dry_run:fail)"
            )

        return sorted(scored, key=lambda p: p['final_score'], reverse=True)
