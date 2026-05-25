"""
PlacementController Celery Tasks
===================================
Two tasks:

1. run_placement_controller_task (every 5 minutes):
   Runs a full PlacementController cycle for a cluster.
   Concurrency-safe via Redis NX lock.
   Shadow mode aware — emits metrics only when shadow flag is set.

2. recover_stale_stateful_migrations (on startup / hourly):
   Scans Redis action queue for in-flight SCALE_WORKLOAD actions whose
   original_replicas was never restored (auto-rebalancer crashed mid-rollout).
   Reconciles replicas back to original count if the new pod is not on Spot.
   Required by §9 Risk 1 mitigation.
"""

import json
import logging
import time
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy.orm import Session

from backend.db.session import SessionLocal
from backend.core.redis_client import get_redis_client
from backend.core.config import settings
from backend.pipeline.stage3_ppe.controller_service import (
    PlacementController,
    SHADOW_MODE_KEY_TEMPLATE,
    METRICS_KEY_TEMPLATE,
)
from backend.services.placement_rollout_service import PlacementRolloutService
from backend.models.cluster import Cluster

logger = logging.getLogger(__name__)
redis_client = get_redis_client()

# ---------------------------------------------------------------------------
# Lock key — prevents concurrent cycles for same cluster
# ---------------------------------------------------------------------------
PC_LOCK_KEY_TEMPLATE = "spot:placement_controller:cycle_lock:{cluster_id}"
PC_LOCK_TTL_SECONDS = 300   # 5 minutes — same as cycle interval


# ---------------------------------------------------------------------------
# Task 0 — Beat dispatcher (enumerates clusters, dispatches per-cluster tasks)
# ---------------------------------------------------------------------------

@shared_task(name="dispatch_placement_controller_cycles", bind=True, max_retries=0)
def dispatch_placement_controller_cycles(self):
    """
    Beat entry point — runs every 5 minutes.

    Queries all clusters with agent_installed=True and dispatches one
    run_placement_controller_task per cluster asynchronously.
    This matches the existing pattern used by placement_advisor_task.

    Only dispatches when FEATURE_PLACEMENT_CONTROLLER_ENABLED is True.
    """
    if not getattr(settings, "FEATURE_PLACEMENT_CONTROLLER_ENABLED", False):
        logger.debug("placement_controller_disabled_globally")
        return "skipped - feature disabled"

    db: Session = SessionLocal()
    try:
        clusters = (
            db.query(Cluster)
            .filter(Cluster.agent_installed == "Y")
            .all()
        )
        dispatched = 0
        for cluster in clusters:
            run_placement_controller_task.apply_async(
                args=[cluster.id],
                queue="default",
            )
            dispatched += 1

        logger.info(
            "placement_controller_dispatch_done",
            extra={"dispatched": dispatched},
        )
        return f"dispatched {dispatched} clusters"
    except Exception as exc:
        logger.exception("placement_controller_dispatch_error", extra={"error": str(exc)})
        return f"error - {exc}"
    finally:
        db.close()


@shared_task(name="dispatch_placement_controller_recovery", bind=True, max_retries=0)
def dispatch_placement_controller_recovery(self):
    """
    Hourly beat entry — dispatches recover_stale_stateful_migrations and
    revalidate_pending_completions per cluster.
    §9 Risk 1 mitigation + needs_revalidation dead-flag scan.
    """
    db: Session = SessionLocal()
    try:
        clusters = (
            db.query(Cluster)
            .filter(Cluster.agent_installed == "Y")
            .all()
        )
        for cluster in clusters:
            recover_stale_stateful_migrations.apply_async(
                args=[cluster.id],
                queue="default",
            )
            revalidate_pending_completions.apply_async(
                args=[cluster.id],
                queue="default",
            )
        return f"dispatched recovery for {len(clusters)} clusters"
    except Exception as exc:
        logger.exception("placement_controller_recovery_dispatch_error", extra={"error": str(exc)})
        return f"error - {exc}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Task 2b — Revalidate optimistically-completed EVICT_POD actions
# ---------------------------------------------------------------------------

@shared_task(name="revalidate_pending_completions", bind=True, max_retries=0)
def revalidate_pending_completions(self, cluster_id: str):
    """
    Scans COMPLETED EVICT_POD AgentActions whose result contains
    needs_revalidation=true (set when the K8s API was unreachable or the
    pod was still Pending at validation time) and re-checks actual pod
    placement via get_pod_placement().

    If the pod now shows on OD → marks FAILED so PlacementController detects
    drift and re-dispatches on its next 5-minute cycle.
    If on Spot or still missing → clears the flag and leaves COMPLETED.
    """
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.pipeline.stage3_ppe.controller_service import get_pod_placement, _mark_for_retry, _decr_semaphore

    db: Session = SessionLocal()
    _redis = redis_client
    revalidated = 0
    corrected = 0
    try:
        candidates = (
            db.query(AgentAction)
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.EVICT_POD,
                AgentAction.status == AgentActionStatus.COMPLETED,
                AgentAction.result["needs_revalidation"].astext == "true",
            )
            .limit(50)
            .all()
        )
        for action in candidates:
            revalidated += 1
            pod_name  = action.payload.get("pod_name") or action.payload.get("pod")
            namespace = action.payload.get("namespace", "default")
            workload_id = action.payload.get("workload_id", "")
            target_cap  = (action.result or {}).get("target_capacity_type", "spot")
            try:
                placement = get_pod_placement(namespace, pod_name)
            except Exception as exc:
                logger.warning(
                    f"[PCRecovery] revalidate: K8s API error for pod={pod_name}: {exc} — skipping"
                )
                continue
            if placement is None:
                # Pod gone or still Pending — clear flag, leave COMPLETED
                action.result = {**(action.result or {}), "needs_revalidation": False}
                db.commit()
                continue
            if placement.capacity_type != target_cap:
                logger.warning(
                    f"[PCRecovery] pod={pod_name} confirmed on {placement.capacity_type} "
                    f"(target={target_cap}) — marking FAILED for drift re-dispatch"
                )
                _mark_for_retry(action, workload_id, db, _redis)
                corrected += 1
            else:
                # Now confirmed on Spot — clear the flag
                action.result = {**(action.result or {}), "needs_revalidation": False}
                db.commit()
        logger.info(
            f"[PCRecovery] revalidate_pending_completions cluster={cluster_id}: "
            f"scanned={revalidated} corrected={corrected}"
        )
        return f"revalidated={revalidated} corrected={corrected}"
    except Exception as exc:
        logger.exception("revalidate_pending_completions_error", extra={"cluster_id": cluster_id, "error": str(exc)})
        return f"error - {exc}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Task 1 — Main 5-minute cycle
# ---------------------------------------------------------------------------

@shared_task(name="run_placement_controller_task", bind=True, max_retries=1)
def run_placement_controller_task(self, cluster_id: str):
    """
    Runs PlacementController.run_cycle() for a single cluster.

    - Guarded by a Redis NX lock to prevent overlapping cycles.
    - Shadow mode: if spot:placement_controller:shadow_mode:{cluster_id} is set,
      controller emits metrics only (no EVICT_POD actions written).
    - Respects FEATURE_PLACEMENT_CONTROLLER_ENABLED setting.
    """
    if not getattr(settings, "FEATURE_PLACEMENT_CONTROLLER_ENABLED", False):
        logger.debug(
            "placement_controller_disabled",
            extra={"cluster_id": cluster_id},
        )
        return "skipped - feature disabled"

    lock_key = PC_LOCK_KEY_TEMPLATE.format(cluster_id=cluster_id)
    acquired = redis_client.set(lock_key, "locked", nx=True, ex=PC_LOCK_TTL_SECONDS)
    if not acquired:
        logger.warning(
            "placement_controller_cycle_already_running",
            extra={"cluster_id": cluster_id},
        )
        return "skipped - locked"

    db: Session = SessionLocal()
    start = time.monotonic()

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(
                "placement_controller_cluster_not_found",
                extra={"cluster_id": cluster_id},
            )
            return "error - cluster not found"

        shadow_mode = bool(
            redis_client.get(
                SHADOW_MODE_KEY_TEMPLATE.format(cluster_id=cluster_id)
            )
        )
        if shadow_mode:
            logger.info(
                "placement_controller_shadow_mode_active",
                extra={"cluster_id": cluster_id},
            )

        rollout_svc = PlacementRolloutService(db, redis_client)

        controller = PlacementController(
            db=db,
            redis=redis_client,
            k8s_client=_get_k8s_client(cluster),
            rollout_svc=rollout_svc,
        )
        controller.run_cycle(cluster_id)

        duration = time.monotonic() - start
        logger.info(
            "placement_controller_cycle_done",
            extra={
                "cluster_id": cluster_id,
                "duration_ms": int(duration * 1000),
                "shadow_mode": shadow_mode,
            },
        )
        return f"success - {duration:.2f}s (shadow={shadow_mode})"

    except Exception as exc:
        logger.exception(
            "placement_controller_cycle_failed",
            extra={"cluster_id": cluster_id, "error": str(exc)},
        )
        _record_failure_metric(cluster_id, str(exc))
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
        redis_client.delete(lock_key)


# ---------------------------------------------------------------------------
# Task 2 — Stale migration recovery (§9 Risk 1)
# ---------------------------------------------------------------------------

@shared_task(name="recover_stale_stateful_migrations", bind=True, max_retries=0)
def recover_stale_stateful_migrations(self, cluster_id: str):
    """
    §9 Risk 1 mitigation: Reconcile workloads whose replica count was incremented
    by a stateful rollout but the rollout never completed (e.g., crash during
    wait_for_new_replica_ready).

    Scans the Redis action queue for SCALE_WORKLOAD actions with
    action_metadata.stateful_strategy = "create_before_delete" that were
    enqueued but not consumed. For each, checks if:
      - Current ready_replicas == original_replicas + 1 (scale-up was applied)
      - The newest pod is NOT on Spot (migration did not complete successfully)

    If stale migration detected: scale back to original_replicas.
    """
    queue_key = f"spot:placement_controller:action_queue:{cluster_id}"
    db: Session = SessionLocal()
    rollout_svc = PlacementRolloutService(db, redis_client)

    try:
        raw_actions = redis_client.lrange(queue_key, 0, -1)
        for raw in raw_actions:
            try:
                action = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if action.get("type") != "SCALE_WORKLOAD":
                continue

            metadata = action.get("action_metadata", {})
            if metadata.get("stateful_strategy") != "create_before_delete":
                continue

            original_replicas = metadata.get("original_replicas")
            workload_id = f"{action.get('namespace', 'default')}/{action.get('name', '')}"
            if not original_replicas or not workload_id:
                continue

            state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
            state_raw = redis_client.get(state_key)
            if not state_raw:
                continue

            try:
                state = json.loads(state_raw)
                current_replicas = int(state.get("replicas", 0))
                ready_replicas = int(state.get("ready_replicas", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

            # Stale detection: replicas are still at original + 1
            # and the newest pod is NOT on Spot (migration did not complete)
            if current_replicas != original_replicas + 1:
                continue

            new_pod_on_spot = rollout_svc._new_pod_placed_on_spot(
                cluster_id, workload_id, original_replicas
            )
            if new_pod_on_spot:
                # Migration completed but replica was never scaled back
                # (auto-rebalancer crashed after Spot placement, before eviction)
                # Do not scale down — eviction will happen on next cycle
                logger.info(
                    "stale_migration_recovery_skip",
                    extra={
                        "cluster_id": cluster_id,
                        "workload_id": workload_id,
                        "reason": "new pod is on Spot — eviction pending next cycle",
                    },
                )
                continue

            # Rollback: new pod is on OD — migration did not improve placement
            logger.warning(
                "stale_migration_recovery_rollback",
                extra={
                    "cluster_id": cluster_id,
                    "workload_id": workload_id,
                    "current_replicas": current_replicas,
                    "original_replicas": original_replicas,
                },
            )
            rollout_svc._scale_workload(cluster_id, workload_id, original_replicas)
            rollout_svc._apply_migration_cooldown(
                cluster_id, workload_id, minutes=30
            )

        return "recovery scan complete"

    except Exception as exc:
        logger.exception(
            "stale_migration_recovery_error",
            extra={"cluster_id": cluster_id, "error": str(exc)},
        )
        return f"error - {exc}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_k8s_client(cluster):
    """
    Returns a K8s API client for the given cluster.
    Stubbed — replace with actual kubeconfig/in-cluster credential load.
    """
    class _StubK8sClient:
        def get_deployment_rollout_status(self, namespace, name):
            return None  # No-op stub; real impl calls AppsV1Api
    return _StubK8sClient()


def _record_failure_metric(cluster_id: str, error: str) -> None:
    try:
        key = METRICS_KEY_TEMPLATE.format(cluster_id=cluster_id)
        redis_client.hset(
            key,
            mapping={
                "cycle_ts": datetime.now(tz=timezone.utc).isoformat(),
                "skipped_reason": f"error:{error[:120]}",
            },
        )
    except Exception:
        pass
