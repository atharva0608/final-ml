"""
Optimizer Coordinator Celery Tasks
===================================

Implements phased optimization timing strategy from problems.md:
- Pool optimization: Every 30 minutes
- Rightsizing evaluation: Every 24 hours
- Combined evaluation: Event-driven (when proposals created)
"""

from celery import shared_task
from sqlalchemy.orm import Session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@shared_task(name='workers.optimizer.pool_optimization', bind=True)
def pool_optimization_worker(self):
    """
    Pool optimization worker - runs every 30 minutes.

    Checks each cluster's optimizer state and only runs pool optimization
    if cluster is in allowed phase (INITIAL_POOL_OPTIMIZATION, STABILIZATION, or COOLDOWN).

    Per problems.md timing strategy:
    - Spot ML runs every 30 min
    - Only changes pool, never changes instance size
    - Safe to run frequently
    """
    from backend.models.base import get_db_contextmanager
    from backend.services.optimizer_coordinator import OptimizerCoordinator
    from backend.models.cluster import Cluster
    from backend.models.optimizer_state import OptimizationPhase
    from backend.core.redis_client import get_redis_client

    logger.info("[OPTIMIZER] Starting pool optimization worker")

    with get_db_contextmanager() as db:
        redis = get_redis_client()
        coordinator = OptimizerCoordinator(db, redis)

        # Get all active clusters
        clusters = db.query(Cluster).filter(
            Cluster.status.in_(["ACTIVE", "DISCOVERED"])
        ).all()

        logger.info(f"[OPTIMIZER] Found {len(clusters)} active clusters")

        for cluster in clusters:
            try:
                # ── Toggle gate: only run if auto_rebalance_enabled ──────────
                opt_settings = cluster.optimization_settings
                auto_rebalance = getattr(opt_settings, 'auto_rebalance_enabled', False) if opt_settings else False
                if not auto_rebalance:
                    logger.debug(f"[OPTIMIZER] Pool optimization skipped for {cluster.name}: auto_rebalance_enabled=False")
                    continue

                # Check if pool optimization is allowed by phase
                can_run, reason = coordinator.can_run_pool_optimization(cluster.id)

                if not can_run:
                    logger.debug(f"[OPTIMIZER] Skipping pool optimization for {cluster.name}: {reason}")
                    continue

                logger.info(f"[OPTIMIZER] Running pool optimization for {cluster.name} (Mode: {'COMBINED' if getattr(opt_settings, 'auto_rightsizing_enabled', False) else 'REBALANCE_ONLY'})")

                # TODO: Execute actual pool optimization
                # This would call: pool_ranking_service.rank_pools() and apply best pool
                # For now, just record that optimization ran
                coordinator.record_pool_optimization(cluster.id)

                logger.info(f"[OPTIMIZER] Completed pool optimization for {cluster.name}")

            except Exception as e:
                logger.error(f"[OPTIMIZER] Failed pool optimization for {cluster.name}: {e}")
                continue

    logger.info("[OPTIMIZER] Pool optimization worker completed")
    return {"status": "success"}


@shared_task(name='workers.optimizer.rightsizing_evaluation', bind=True)
def rightsizing_evaluation_worker(self):
    """
    Rightsizing evaluation worker - runs every 24 hours.

    Checks each cluster's optimizer state and only runs rightsizing evaluation
    if cluster has completed ≥1 hour stabilization.

    Per problems.md timing strategy:
    - Rightsizing evaluation runs once per day
    - Requires ≥24 hour stability window
    - Only proposes, does not execute
    - Coordinator evaluates proposals with combined EV
    """
    from backend.models.base import get_db_contextmanager
    from backend.services.optimizer_coordinator import OptimizerCoordinator
    from backend.services.rightsizing_service import RightSizingService
    from backend.models.cluster import Cluster
    from backend.core.redis_client import get_redis_client

    logger.info("[OPTIMIZER] Starting rightsizing evaluation worker")

    with get_db_contextmanager() as db:
        redis = get_redis_client()
        coordinator = OptimizerCoordinator(db, redis)
        rightsizing_svc = RightSizingService(db)

        # Get all active clusters
        clusters = db.query(Cluster).filter(
            Cluster.status.in_(["ACTIVE", "DISCOVERED"])
        ).all()

        logger.info(f"[OPTIMIZER] Found {len(clusters)} active clusters for rightsizing evaluation")

        proposals_created = 0

        for cluster in clusters:
            try:
                # ── Toggle gate: only run if auto_rightsizing_enabled ─────────
                opt_settings = cluster.optimization_settings
                auto_rightsizing = getattr(opt_settings, 'auto_rightsizing_enabled', False) if opt_settings else False
                if not auto_rightsizing:
                    logger.debug(f"[OPTIMIZER] Rightsizing skipped for {cluster.name}: auto_rightsizing_enabled=False")
                    continue

                # Also block if rebalance is running (pool-first in Mode 1)
                auto_rebalance = getattr(opt_settings, 'auto_rebalance_enabled', False) if opt_settings else False
                if auto_rebalance:
                    # Mode 1 (COMBINED): rightsizing must wait for pool stabilization
                    can_pool_run, pool_reason = coordinator.can_run_pool_optimization(cluster.id)
                    if can_pool_run:
                        # Pool optimization hasn't run yet — rightsizing defers
                        logger.info(f"[OPTIMIZER] Mode 1 (COMBINED): deferring rightsizing for {cluster.name} until pool stabilizes")
                        continue

                # Check if rightsizing evaluation is allowed by phase
                can_run, reason = coordinator.can_run_rightsizing_evaluation(cluster.id)

                if not can_run:
                    logger.debug(f"[OPTIMIZER] Skipping rightsizing for {cluster.name}: {reason}")
                    continue

                logger.info(f"[OPTIMIZER] Running rightsizing evaluation for {cluster.name} (Mode: {'COMBINED' if auto_rebalance else 'RIGHTSIZING_ONLY'})")

                # Create rightsizing proposals (does not execute)
                proposal_ids = rightsizing_svc.create_rightsizing_proposals(
                    cluster_id=cluster.id,
                    min_savings_pct=10.0,  # Minimum 10% savings required
                    stability_window_hours=24  # Require 24-hour metrics
                )

                if proposal_ids:
                    logger.info(f"[OPTIMIZER] Created {len(proposal_ids)} proposal(s) for {cluster.name}")
                    proposals_created += len(proposal_ids)

                    # Record evaluation and trigger combined evaluation
                    coordinator.record_rightsizing_evaluation(cluster.id, proposal_ids[0])

                    # Trigger event-driven evaluation
                    evaluate_proposal_task.delay(proposal_ids[0])
                else:
                    logger.info(f"[OPTIMIZER] No rightsizing opportunities for {cluster.name}")
                    coordinator.record_rightsizing_evaluation(cluster.id, None)

            except Exception as e:
                logger.error(f"[OPTIMIZER] Failed rightsizing evaluation for {cluster.name}: {e}")
                continue

    logger.info(f"[OPTIMIZER] Rightsizing evaluation worker completed: {proposals_created} proposals created")
    return {"status": "success", "proposals_created": proposals_created}


@shared_task(name='workers.optimizer.evaluate_proposal', bind=True)
def evaluate_proposal_task(self, proposal_id: str):
    """
    Evaluate a rightsizing proposal using combined EV calculation.

    Event-driven task triggered when a proposal is created.
    Compares Option A (size+pool) vs B (new pool) vs C (nothing).

    Args:
        proposal_id: Rightsizing proposal ID to evaluate
    """
    from backend.models.base import get_db_contextmanager
    from backend.services.optimizer_coordinator import OptimizerCoordinator
    from backend.core.redis_client import get_redis_client

    logger.info(f"[OPTIMIZER] Evaluating proposal {proposal_id}")

    with get_db_contextmanager() as db:
        redis = get_redis_client()
        coordinator = OptimizerCoordinator(db, redis)

        try:
            result = coordinator.evaluate_combined_proposal(proposal_id)

            if result["approved"]:
                logger.info(
                    f"[OPTIMIZER] Proposal {proposal_id} APPROVED: "
                    f"Option {result['selected_option']} - {result['reason']}"
                )
            else:
                logger.info(
                    f"[OPTIMIZER] Proposal {proposal_id} REJECTED: {result['reason']}"
                )

            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"[OPTIMIZER] Failed to evaluate proposal {proposal_id}: {e}")
            return {"status": "error", "error": str(e)}


@shared_task(name='workers.optimizer.execute_approved_proposal', bind=True)
def execute_approved_proposal_task(self, proposal_id: str):
    """
    Execute an approved rightsizing proposal.

    This task is manually triggered by user approval or can be automated
    if cluster has auto-execution enabled.

    Args:
        proposal_id: Rightsizing proposal ID to execute
    """
    from backend.models.base import get_db_contextmanager
    from backend.services.optimizer_coordinator import OptimizerCoordinator
    from backend.core.redis_client import get_redis_client

    logger.info(f"[OPTIMIZER] Executing approved proposal {proposal_id}")

    with get_db_contextmanager() as db:
        redis = get_redis_client()
        coordinator = OptimizerCoordinator(db, redis)

        try:
            result = coordinator.execute_approved_proposal(proposal_id)

            if result["success"]:
                logger.info(f"[OPTIMIZER] Proposal {proposal_id} executed successfully")
            else:
                logger.error(f"[OPTIMIZER] Proposal {proposal_id} execution failed: {result['reason']}")

            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"[OPTIMIZER] Failed to execute proposal {proposal_id}: {e}")
            return {"status": "error", "error": str(e)}
