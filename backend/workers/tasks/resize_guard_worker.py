"""
Post-Resize Guard Worker (Enhancement 4 & 9)
=============================================

Monitors cluster health for 2 hours after any resize action.
If CPU > 85% sustained 10 min or OOM events detected → rollback.

Also implements observability-driven rollback by checking:
- Pod restart rate (2x baseline triggers rollback)
- Memory pressure events
- Sustained CPU stress

Runs every 5 minutes via Celery Beat.
"""
from celery import shared_task
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='workers.optimizer.resize_guard', bind=True)
def resize_guard_worker(self):
    """Runs every 5 minutes, checks clusters with recent resize actions."""
    from backend.models.base import get_db_contextmanager
    from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus
    from backend.core.redis_client import get_redis_client

    with get_db_contextmanager() as db:
        redis = get_redis_client()

        # Find proposals executed in last 2 hours
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        recent_executions = db.query(RightsizingProposal).filter(
            RightsizingProposal.status == ProposalStatus.EXECUTED,
            RightsizingProposal.executed_at >= two_hours_ago
        ).all()

        logger.info(f"[RESIZE-GUARD] Monitoring {len(recent_executions)} recent executions")

        for proposal in recent_executions:
            cluster_id = proposal.cluster_id
            guard_key = f"resize:guard:{cluster_id}"

            # Track guard invocations
            invocation_count = redis.incr(f"{guard_key}:invocations")
            if invocation_count == 1:
                redis.expire(f"{guard_key}:invocations", 7200)  # 2 hours

            # ── CPU STRESS CHECK ──────────────────────────────────────────
            cpu_key = f"metrics:cpu_avg_10m:{cluster_id}"
            cpu_avg = redis.get(cpu_key)

            if cpu_avg and float(cpu_avg) > 85.0:
                logger.warning(
                    f"[RESIZE-GUARD] CPU > 85% for cluster {cluster_id} "
                    f"after resize (current: {float(cpu_avg):.1f}%). Marking for rollback review."
                )
                redis.setex(f"resize:rollback_needed:{cluster_id}", 3600, "cpu_stress")

                # Record in proposal
                proposal.status = ProposalStatus.FAILED
                proposal.rejection_reason = f"Post-resize CPU stress: {float(cpu_avg):.1f}%"
                db.commit()

                logger.error(f"[RESIZE-GUARD] Proposal {proposal.id} failed due to CPU stress")
                continue

            # ── OBSERVABILITY-DRIVEN ROLLBACK (Enhancement 9) ─────────────
            # Check pod restart rate (2x baseline triggers rollback)
            restart_key = f"metrics:pod_restarts_10m:{cluster_id}"
            restart_rate = redis.get(restart_key)
            baseline_key = f"metrics:pod_restart_baseline:{cluster_id}"
            baseline = redis.get(baseline_key)

            if restart_rate and baseline:
                current_restarts = float(restart_rate)
                baseline_restarts = float(baseline)

                if current_restarts > baseline_restarts * 2.0:
                    logger.warning(
                        f"[RESIZE-GUARD] Pod restart rate 2x baseline for {cluster_id} "
                        f"(current: {current_restarts:.1f}, baseline: {baseline_restarts:.1f})"
                    )
                    redis.setex(f"resize:rollback_needed:{cluster_id}", 3600, "restart_spike")

                    proposal.status = ProposalStatus.FAILED
                    proposal.rejection_reason = (
                        f"Post-resize restart spike: {current_restarts:.1f} "
                        f"(baseline: {baseline_restarts:.1f})"
                    )
                    db.commit()

                    logger.error(
                        f"[RESIZE-GUARD] Proposal {proposal.id} failed due to restart spike"
                    )
                    continue

            # ── MEMORY PRESSURE CHECK ─────────────────────────────────────
            memory_key = f"metrics:memory_pressure_events:{cluster_id}"
            pressure_events = redis.get(memory_key)

            if pressure_events and int(pressure_events) > 5:
                logger.warning(
                    f"[RESIZE-GUARD] Memory pressure events detected for {cluster_id} "
                    f"({pressure_events} events)"
                )
                redis.setex(f"resize:rollback_needed:{cluster_id}", 3600, "memory_pressure")

                proposal.status = ProposalStatus.FAILED
                proposal.rejection_reason = f"Post-resize memory pressure: {pressure_events} events"
                db.commit()

                logger.error(
                    f"[RESIZE-GUARD] Proposal {proposal.id} failed due to memory pressure"
                )
                continue

            # ── MODE 3 SYNERGY: Pool-risk revert (Task 2.8) ───────────────
            # When both rebalancing and rightsizing are active for a cluster,
            # a resize can put a node onto a riskier pool that the rebalancer
            # is simultaneously trying to *leave*.  Detect this conflict by
            # comparing the post-resize pool risk score against the cluster's
            # configured risk ceiling.
            try:
                from backend.models.cluster import Cluster
                _cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
                if _cluster and getattr(_cluster, 'auto_rebalance_enabled', False) and getattr(_cluster, 'auto_rightsizing_enabled', False):
                    # Both features active → synergy guard applies
                    _risk_key = f"pool:risk_score:{cluster_id}:{proposal.instance_type or 'unknown'}"
                    _pool_risk = redis.get(_risk_key)
                    _ceiling_key = f"cluster:{cluster_id}:risk_ceiling_pct"
                    _ceiling = redis.get(_ceiling_key)
                    _ceiling_val = float(_ceiling) if _ceiling else 20.0  # default BALANCED ceiling

                    if _pool_risk and float(_pool_risk) > _ceiling_val:
                        logger.warning(
                            f"[RESIZE-GUARD] Mode 3 synergy: pool risk {float(_pool_risk):.1f}% "
                            f"> ceiling {_ceiling_val:.1f}% for cluster {cluster_id}"
                        )
                        redis.setex(f"resize:rollback_needed:{cluster_id}", 3600, "pool_risk_synergy")

                        proposal.status = ProposalStatus.FAILED
                        proposal.rejection_reason = (
                            f"Synergy guard: pool risk {float(_pool_risk):.1f}% "
                            f"exceeds ceiling {_ceiling_val:.1f}%"
                        )
                        db.commit()

                        logger.error(
                            f"[RESIZE-GUARD] Proposal {proposal.id} failed due to "
                            f"pool risk synergy conflict"
                        )
                        continue
            except Exception as _synergy_err:
                logger.debug(f"[RESIZE-GUARD] Synergy check skipped: {_synergy_err}")

            # If all checks pass, log success
            logger.debug(
                f"[RESIZE-GUARD] Cluster {cluster_id} healthy "
                f"(invocation {invocation_count}/24)"
            )

        logger.info(f"[RESIZE-GUARD] Guard cycle complete")


@shared_task(name='workers.optimizer.update_pod_restart_baseline', bind=True)
def update_pod_restart_baseline(self):
    """
    Updates pod restart baseline every hour.
    Baseline = average restarts over last 24h (excluding last 2h guard window).
    """
    from backend.models.base import get_db_contextmanager
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.core.redis_client import get_redis_client

    with get_db_contextmanager() as db:
        redis = get_redis_client()

        active_clusters = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).all()

        logger.info(f"[BASELINE-UPDATE] Updating baseline for {len(active_clusters)} clusters")

        for cluster in active_clusters:
            cluster_id = cluster.id

            # Get restart counts over last 24h (excluding recent 2h)
            restart_samples = []
            for hour_offset in range(2, 26):  # 2-26 hours ago
                key = f"metrics:pod_restarts_1h:{cluster_id}:{hour_offset}h_ago"
                count = redis.get(key)
                if count:
                    restart_samples.append(float(count))

            if restart_samples:
                baseline = sum(restart_samples) / len(restart_samples)
                baseline_key = f"metrics:pod_restart_baseline:{cluster_id}"
                redis.setex(baseline_key, 3600, str(baseline))  # 1 hour TTL
                logger.debug(
                    f"[BASELINE-UPDATE] Cluster {cluster_id}: baseline={baseline:.2f} "
                    f"(from {len(restart_samples)} samples)"
                )

        logger.info("[BASELINE-UPDATE] Baseline update complete")


@shared_task(name='workers.optimizer.resize_rollback_consumer', bind=True)
def resize_rollback_consumer(self):
    """
    Consumer for `resize:rollback_needed:{cluster_id}` keys.
    When resize_guard_worker detects a problem (CPU stress, restart spike, memory pressure),
    it sets the rollback key. This task reads the key, finds the original resources from
    the rightsize_monitor cache, and creates a PATCH_CONTAINER_RESOURCES AgentAction to
    revert the workload to its pre-resize resource values.

    Runs every 60 seconds via Celery Beat.
    """
    from backend.models.base import get_db_contextmanager
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus
    from backend.core.redis_client import get_redis_client
    import json
    import uuid

    with get_db_contextmanager() as db:
        redis = get_redis_client()

        # Find clusters that have a rollback_needed key
        active_clusters = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).all()

        rolled_back = 0

        for cluster in active_clusters:
            cluster_id = cluster.id
            rollback_key = f"resize:rollback_needed:{cluster_id}"
            rollback_reason = redis.get(rollback_key)

            if not rollback_reason:
                continue

            if isinstance(rollback_reason, bytes):
                rollback_reason = rollback_reason.decode('utf-8')

            logger.warning(
                f"[ROLLBACK-CONSUMER] Rollback needed for cluster {cluster_id}: {rollback_reason}"
            )

            # Find recently executed proposals for this cluster that were marked FAILED
            recent_proposals = db.query(RightsizingProposal).filter(
                RightsizingProposal.cluster_id == cluster_id,
                RightsizingProposal.status == ProposalStatus.FAILED,
            ).order_by(RightsizingProposal.executed_at.desc()).limit(5).all()

            for proposal in recent_proposals:
                # Look for original resources in the rightsize_monitor cache
                _ctrl_key = f"spot:rightsize_monitor:{cluster_id}:{proposal.namespace}/{proposal.controller_name}" if hasattr(proposal, 'namespace') else None
                _original_raw = redis.get(_ctrl_key) if _ctrl_key else None

                if not _original_raw:
                    # Try broader search: check action_metadata for original_resources
                    try:
                        from backend.models.agent_action import AgentAction
                        _recent_action = db.query(AgentAction).filter(
                            AgentAction.cluster_id == cluster_id,
                            AgentAction.action_type == 'PATCH_CONTAINER_RESOURCES',
                            AgentAction.status == 'COMPLETED',
                        ).order_by(AgentAction.completed_at.desc()).first()

                        if _recent_action and _recent_action.result:
                            _result = _recent_action.result if isinstance(_recent_action.result, dict) else json.loads(_recent_action.result)
                            _original_raw = json.dumps(_result.get('original_resources')) if _result.get('original_resources') else None
                    except Exception as _find_err:
                        logger.debug(f"[ROLLBACK-CONSUMER] Could not find original resources from action: {_find_err}")

                if not _original_raw:
                    logger.warning(
                        f"[ROLLBACK-CONSUMER] No original resources found for proposal {proposal.id} "
                        f"in cluster {cluster_id} — cannot auto-rollback"
                    )
                    continue

                try:
                    original_resources = json.loads(_original_raw) if isinstance(_original_raw, (str, bytes)) else _original_raw
                except (json.JSONDecodeError, TypeError):
                    logger.error(f"[ROLLBACK-CONSUMER] Invalid original_resources JSON for proposal {proposal.id}")
                    continue

                # Create rollback AgentAction
                try:
                    from backend.models.agent_action import AgentAction
                    rollback_action = AgentAction(
                        id=str(uuid.uuid4()),
                        cluster_id=cluster_id,
                        action_type='PATCH_CONTAINER_RESOURCES',
                        status='PENDING',
                        payload=json.dumps({
                            'namespace': getattr(proposal, 'namespace', 'default'),
                            'controller_type': getattr(proposal, 'controller_type', 'Deployment'),
                            'controller_name': getattr(proposal, 'controller_name', ''),
                            'container_name': getattr(proposal, 'container_name', ''),
                            'resources': original_resources,
                            'is_rollback': True,
                            'rollback_reason': rollback_reason,
                            'original_proposal_id': str(proposal.id),
                        }),
                    )
                    db.add(rollback_action)

                    # Mark proposal as rolled back
                    proposal.status = ProposalStatus.ROLLED_BACK if hasattr(ProposalStatus, 'ROLLED_BACK') else ProposalStatus.FAILED
                    proposal.rejection_reason = (proposal.rejection_reason or '') + f' → Rollback issued ({rollback_reason})'

                    db.commit()

                    rolled_back += 1
                    logger.info(
                        f"[ROLLBACK-CONSUMER] Created rollback action {rollback_action.id} "
                        f"for proposal {proposal.id} in cluster {cluster_id}"
                    )

                except Exception as _create_err:
                    logger.error(f"[ROLLBACK-CONSUMER] Failed to create rollback action: {_create_err}")
                    db.rollback()
                    continue

            # Delete the rollback key so we don't re-process
            redis.delete(rollback_key)

        if rolled_back:
            logger.info(f"[ROLLBACK-CONSUMER] Issued {rolled_back} rollback action(s)")
        else:
            logger.debug("[ROLLBACK-CONSUMER] No rollbacks needed this cycle")
