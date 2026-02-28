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
