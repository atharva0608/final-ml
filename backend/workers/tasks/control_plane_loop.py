"""
Control Plane Loop — 8-Step Decision Cycle
==========================================
Implements problems.md §6: Full decision cycle as a Celery task.

Steps:
  1. Update Market Signals (prices, volatility, advisor data, pool pressure)
  2. Update Blacklist Tiers
  3. Update Cluster Instability State (circuit breaker)
  4. Filter Nodes (stateful, cooldown, policy)
  5. Right-Sizing Baseline
  6. Evaluate Candidate Pools (risk + EV per pool)
  7. Diversification Simulation
  8. Build Execution Plan (sort, apply limits)
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from celery import shared_task
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@shared_task(name="workers.control_plane.run_decision_cycle", bind=True, max_retries=2)
def run_decision_cycle(self, cluster_id: str):
    """
    Full 8-step decision cycle for one cluster.
    Called by Celery beat every 5 minutes per active cluster.
    """
    from backend.models.base import SessionLocal
    from backend.core.redis_client import get_redis_client

    db = SessionLocal()
    redis_client = get_redis_client()

    try:
        controller = ControlPlaneController(db, redis_client)
        result = controller.run_cycle(cluster_id)
        logger.info(
            f"[ControlPlane] Cluster {cluster_id} cycle complete: "
            f"step={result.get('step_completed')}, approved={result.get('approved')}"
        )
        return result
    except Exception as exc:
        logger.error(f"[ControlPlane] Cluster {cluster_id} cycle error: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@shared_task(name="workers.control_plane.run_all_clusters_decision_cycle", bind=True)
def run_all_clusters_decision_cycle(self):
    """
    Trigger decision cycles for all ACTIVE clusters.
    Called by Celery beat every 5 minutes.
    """
    from backend.models.base import SessionLocal
    from backend.models.cluster import Cluster

    db = SessionLocal()
    try:
        clusters = db.query(Cluster).filter(Cluster.status == "ACTIVE").all()
        for cluster in clusters:
            run_decision_cycle.apply_async(args=[str(cluster.id)], queue="control_plane")
        logger.info(f"[ControlPlane] Queued decision cycles for {len(clusters)} clusters")
        return {"queued": len(clusters), "timestamp": datetime.utcnow().isoformat()}
    finally:
        db.close()


class ControlPlaneController:
    """
    Orchestrates the 8-step decision cycle for a cluster.
    """

    def __init__(self, db: Session, redis_client):
        self.db = db
        self.redis = redis_client
        self._init_services()

    def _init_services(self):
        from backend.services.blacklist_service import BlacklistService
        from backend.services.circuit_breaker import CircuitBreaker
        from backend.services.guardrail_engine import evaluate_all_guardrails
        from backend.services.observability_logger import ObservabilityLogger
        from backend.core.risk_engine import compute_pool_risk
        from backend.core.ev_model import evaluate_candidate_ev

        self.blacklist_svc = BlacklistService(self.redis)
        self.circuit_breaker = CircuitBreaker(self.redis)
        self.obs_logger = ObservabilityLogger(self.db, self.redis)
        self.evaluate_guardrails = evaluate_all_guardrails
        self.compute_pool_risk = compute_pool_risk
        self.evaluate_ev = evaluate_candidate_ev

    def run_cycle(self, cluster_id: str) -> dict:
        """Execute the full 8-step decision cycle."""
        from backend.models.cluster import Cluster

        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return {"approved": False, "reason": "Cluster not found", "step_completed": "INIT"}

        # ── SAFETY GATE: Hibernation Early Gate (Task 1.1) ────────
        # Must be the FIRST check — before any Redis reads, pricing
        # fetches, DryRun calls, or risk calculations.
        if getattr(cluster, 'is_hibernating', False):
            logger.info(f"Cluster {cluster_id} is hibernating — skipping cycle")
            return {"status": "SKIPPED", "reason": "HIBERNATING", "approved": False, "step_completed": "HIBERNATION_GATE"}

        region = cluster.region or "us-east-1"

        # ── Step 1: Update Market Signals ─────────────────────────
        market_signals = self._step1_update_market_signals(cluster_id, region)

        # ── Step 2: Update Blacklist Tiers ────────────────────────
        self._step2_update_blacklist_tiers(region)

        # ── Step 3: Update Cluster Instability State ──────────────
        cb_status = self._step3_update_cluster_instability(cluster_id)
        if cb_status.get("state") == "HALT":
            return {
                "approved": False,
                "reason": "Circuit breaker HALT — all automation blocked",
                "step_completed": "STEP_3_CIRCUIT_BREAKER",
                "circuit_breaker": cb_status,
            }

        # ── Step 4: Filter Nodes ──────────────────────────────────
        eligible_nodes = self._step4_filter_nodes(cluster_id, cluster)
        if not eligible_nodes:
            return {
                "approved": False,
                "reason": "No eligible nodes (all stateful/cooldown/policy)",
                "step_completed": "STEP_4_NODE_FILTER",
            }

        # ── Step 5: Right-Sizing Baseline ─────────────────────────
        sizing_baseline = self._step5_rightsizing_baseline(cluster_id)

        # ── Step 6: Evaluate Candidate Pools ─────────────────────
        ranked_candidates = self._step6_evaluate_pools(
            cluster_id, region, market_signals, cb_status
        )
        if not ranked_candidates:
            return {
                "approved": False,
                "reason": "No positive-EV candidates found",
                "step_completed": "STEP_6_POOL_EVALUATION",
            }

        # ── Step 7: Diversification Simulation ───────────────────
        approved_candidates = self._step7_diversification_simulation(
            cluster_id, ranked_candidates
        )

        # ── Step 8: Build Execution Plan ─────────────────────────
        execution_plan = self._step8_build_execution_plan(
            cluster_id, approved_candidates, sizing_baseline
        )

        self.obs_logger.log_decision(
            cluster_id=cluster_id,
            decision_type="DECISION_CYCLE",
            approved=bool(execution_plan.get("actions")),
            reason=f"Cycle complete: {len(execution_plan.get('actions', []))} actions planned",
            market_snapshot=market_signals,
            ev_breakdown={"top_candidates": ranked_candidates[:3]},
        )

        return {
            "approved": bool(execution_plan.get("actions")),
            "step_completed": "STEP_8_EXECUTION_PLAN",
            "execution_plan": execution_plan,
            "circuit_breaker": cb_status,
            "eligible_nodes": len(eligible_nodes),
            "candidates_evaluated": len(ranked_candidates),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Individual step implementations ───────────────────────────

    def _step1_update_market_signals(self, cluster_id: str, region: str) -> dict:
        """Fetch latest spot prices, volatility, advisor data, pool pressure."""
        try:
            # Pull from Redis cache populated by pricing workers
            volatility_key = f"spot:volatility_regime:{region}"
            raw = self.redis.get(volatility_key)
            is_volatile = raw == b"high" if raw else False

            return {
                "region": region,
                "is_volatile": is_volatile,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.warning(f"[Step1] Market signals error: {e}")
            return {"region": region, "is_volatile": False}

    def _step2_update_blacklist_tiers(self, region: str):
        """Cleanup expired blacklist entries."""
        try:
            cleaned = self.blacklist_svc.cleanup_expired(region)
            if cleaned:
                logger.info(f"[Step2] Cleaned {cleaned} expired blacklist entries in {region}")
        except Exception as e:
            logger.warning(f"[Step2] Blacklist cleanup error: {e}")

    def _step3_update_cluster_instability(self, cluster_id: str) -> dict:
        """Auto-recover circuit breaker based on elapsed time."""
        return self.circuit_breaker.check_and_auto_recover(cluster_id)

    def _step4_filter_nodes(self, cluster_id: str, cluster) -> list:
        """Return nodes eligible for optimization (stateless, off cooldown)."""
        try:
            from backend.services.workload_inspector import WorkloadInspector
            inspector = WorkloadInspector(self.db, self.redis)
            classification = inspector.classify_cluster_nodes(cluster_id)
            eligible = [
                n for n in classification.get("nodes", [])
                if n.get("workload_type") in ("STATELESS", "STATELESS_ELIGIBLE")
            ]
            return eligible
        except Exception as e:
            logger.warning(f"[Step4] Node filter error: {e}")
            return []

    def _step5_rightsizing_baseline(self, cluster_id: str) -> dict:
        """Compute current sizing baseline for the cluster."""
        try:
            from backend.services.optimizer_coordinator import OptimizerCoordinator
            coordinator = OptimizerCoordinator(self.db, self.redis)
            trust = coordinator.get_cluster_trust_phase(cluster_id)
            return {
                "trust_phase": trust.get("phase", 0),
                "rightsizing_allowed": trust.get("rightsizing_allowed", False),
                "safety_buffer_pct": trust.get("safety_buffer_pct", 30),
            }
        except Exception as e:
            logger.warning(f"[Step5] Sizing baseline error: {e}")
            return {"trust_phase": 0, "rightsizing_allowed": False}

    def _step6_evaluate_pools(
        self, cluster_id: str, region: str, market_signals: dict, cb_status: dict
    ) -> list:
        """Evaluate candidate pools with full risk + EV model."""
        try:
            # Load global rankings from cache
            rankings_key = f"global_pool_rankings:{region}"
            raw = self.redis.get(rankings_key)
            if not raw:
                return []

            import json as _json
            rankings_data = _json.loads(raw)
            pools = rankings_data.get("rankings", [])[:20]  # Top 20

            # ── Task 4.3: Capture ranking version for optimistic lock ──
            ranking_version = rankings_data.get("version", rankings_data.get("generated_at", "unknown"))
            self._ranking_version = ranking_version  # Store for Step 8 hash

            instability_mode = cb_status.get("state", "NORMAL")
            candidates = []

            for pool in pools:
                instance_type = pool.get("instance_type", "")
                az = pool.get("az", "")
                ml_risk = pool.get("risk_probability", 0.5)
                savings = pool.get("predicted_savings", 0.1)

                # Bayesian risk
                risk_result = self.compute_pool_risk(
                    ml_risk=ml_risk,
                    advisor_risk=pool.get("advisor_risk", 0.0),
                    failures_30min=0,
                    active_nodes=max(pool.get("active_nodes", 5), 1),
                    minutes_since_last_event=60.0,
                    az_pool_pressures=[],
                    price_samples_60min=[pool.get("spot_price", 0.05)] * 3,
                    ema_30_price=pool.get("spot_price"),
                    instability_mode=instability_mode,
                )

                # EV
                ev_result = self.evaluate_ev(
                    savings=savings,
                    final_risk=risk_result["final_risk"],
                    normalized_volatility=risk_result["normalized_volatility"],
                )

                if ev_result["is_eligible"]:
                    candidates.append({
                        **pool,
                        "risk_components": risk_result,
                        "ev_breakdown": ev_result,
                        "final_ev": ev_result["ev"],
                    })

            # Sort by EV descending
            candidates.sort(key=lambda x: x["final_ev"], reverse=True)
            return candidates

        except Exception as e:
            logger.warning(f"[Step6] Pool evaluation error: {e}")
            return []

    def _step7_diversification_simulation(
        self, cluster_id: str, candidates: list
    ) -> list:
        """Filter candidates that would violate diversification constraints."""
        try:
            from backend.services.diversity_enforcer import DiversityEnforcer
            enforcer = DiversityEnforcer(self.db, self.redis)
            approved = []
            for c in candidates:
                if enforcer.check_can_add_pool(
                    cluster_id,
                    c.get("instance_type", ""),
                    c.get("az", ""),
                ):
                    approved.append(c)
            return approved
        except Exception as e:
            logger.warning(f"[Step7] Diversification sim error: {e}")
            return candidates  # Pass-through on error

    def _step8_build_execution_plan(
        self, cluster_id: str, candidates: list, sizing_baseline: dict
    ) -> dict:
        """Build final execution plan respecting concurrency limits."""
        import hashlib
        import json as _json

        MAX_CONCURRENT = 3
        actions = candidates[:MAX_CONCURRENT]

        plan = {
            "cluster_id": cluster_id,
            "strategy": "SAVINGS_FIRST",
            "actions": [
                {
                    "instance_type": a.get("instance_type"),
                    "az": a.get("az"),
                    "final_ev": a.get("final_ev"),
                    "estimated_savings": a.get("predicted_savings"),
                    "risk": a.get("risk_components", {}).get("final_risk"),
                }
                for a in actions
            ],
            "concurrency_limit": MAX_CONCURRENT,
            "sizing_baseline": sizing_baseline,
            "created_at": datetime.utcnow().isoformat(),
        }

        # ── Task 4.3: Check ranking version hasn't changed ────────
        ranking_version = getattr(self, '_ranking_version', None)
        if ranking_version:
            current_raw = self.redis.get(f"global_pool_rankings:{plan.get('cluster_id', '')}")
            if current_raw:
                try:
                    current_data = _json.loads(current_raw)
                    current_version = current_data.get("version", current_data.get("generated_at", "unknown"))
                    if current_version != ranking_version:
                        logger.warning(
                            f"[Step8] Ranking version changed {ranking_version} → {current_version}, aborting plan"
                        )
                        return {"actions": [], "reason": "RANKING_VERSION_CHANGED"}
                except Exception:
                    pass
            plan["ranking_version"] = ranking_version

        # ── Task 4.4: Execution plan hash verification ────────────
        plan_hash = hashlib.sha256(
            _json.dumps(plan["actions"], sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        plan["plan_hash"] = plan_hash

        # Store hash in Redis so executor can verify
        self.redis.setex(
            f"spot:execution_plan_hash:{cluster_id}",
            300,  # 5-minute TTL
            plan_hash
        )

        return plan
