"""KEDA Installer Celery Task — K2.5

Async Helm install / uninstall task for KEDA.

The task is queued when the backend dispatches an INSTALL_KEDA or
UNINSTALL_KEDA AgentAction via KedaService.install_keda() /
KedaService.uninstall_keda().

Flow:
  1. Poll the latest pending INSTALL_KEDA / UNINSTALL_KEDA AgentAction.
  2. Verify the action is still PENDING (idempotency guard).
  3. Update action status → PICKED_UP.
  4. Wait up to KEDA_INSTALL_TIMEOUT_S for the in-cluster agent to execute
     the Helm command and report back (via /agents/actions/{id}/result).
  5. Mark the action COMPLETED or FAILED based on callback.
  6. Clear the spot:keda_installing:{cluster_id} Redis flag.

Note: The actual Helm execution happens in agent/actuator.py via the
INSTALL_KEDA / UNINSTALL_KEDA action handlers. This Celery task handles
the async polling and status lifecycle on the backend side.
"""

import json
import time
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy.orm import Session

from backend.workers.app import app
from backend.models.base import get_db
from backend.core.logger import logger
from backend.core.redis_client import get_redis_client

# How long to wait for the agent to complete the Helm install (seconds)
KEDA_INSTALL_TIMEOUT_S = 300   # 5 minutes — Helm chart download + CRD creation
KEDA_POLL_INTERVAL_S   = 10    # Poll action status every 10 seconds


@app.task(name="workers.keda.monitor_install_actions", bind=True, max_retries=3)
def monitor_keda_install_actions(self):
    """
    Periodic task (every 30 s) that checks INSTALL_KEDA / UNINSTALL_KEDA
    AgentActions that are PICKED_UP and handles timeout / completion
    bookkeeping.

    Registered in Celery beat with 30-second interval (see app.py).
    """
    db = next(get_db())
    redis = get_redis_client()
    try:
        _check_pending_keda_actions(db, redis)
    except Exception as exc:
        logger.error(f"[keda_installer] monitor_keda_install_actions failed: {exc}")
    finally:
        db.close()


def _check_pending_keda_actions(db: Session, redis):
    """
    Core logic — process PENDING and PICKED_UP KEDA install/uninstall actions.
    """
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # Fetch all recent KEDA install/uninstall actions in PENDING or PICKED_UP state
    actions = (
        db.query(AgentAction)
        .filter(
            AgentAction.action_type.in_([
                AgentActionType.INSTALL_KEDA,
                AgentActionType.UNINSTALL_KEDA,
            ]),
            AgentAction.status.in_([
                AgentActionStatus.PENDING,
                AgentActionStatus.PICKED_UP,
            ]),
        )
        .order_by(AgentAction.created_at.desc())
        .limit(20)
        .all()
    )

    if not actions:
        return

    logger.info(f"[keda_installer] Processing {len(actions)} KEDA install action(s)")

    for action in actions:
        cluster_id    = str(action.cluster_id)
        install_key   = f"spot:keda_installing:{cluster_id}"
        action_type   = (
            action.action_type.value
            if hasattr(action.action_type, "value")
            else str(action.action_type)
        )

        # Compute age of the action
        created = action.created_at or datetime.utcnow()
        age_s   = (datetime.utcnow() - created).total_seconds()

        # ── Timeout guard ─────────────────────────────────────────────────────
        if age_s > KEDA_INSTALL_TIMEOUT_S:
            logger.warning(
                f"[keda_installer] Action {action.id} ({action_type}) timed out "
                f"after {age_s:.0f}s for cluster {cluster_id}"
            )
            action.status = AgentActionStatus.FAILED
            _result = action.result or {}
            _result["failure_reason"] = (
                f"Timed out after {KEDA_INSTALL_TIMEOUT_S}s — "
                "agent did not report back"
            )
            action.result = _result
            db.commit()

            # Clear installing flag so detection recovers
            if redis:
                try:
                    redis.delete(install_key)
                except Exception:
                    pass
            continue

        # ── Transition PENDING → PICKED_UP ────────────────────────────────────
        if action.status == AgentActionStatus.PENDING:
            action.status = AgentActionStatus.PICKED_UP
            db.commit()
            logger.info(
                f"[keda_installer] Marked action {action.id} ({action_type}) "
                f"PICKED_UP for cluster {cluster_id}"
            )
            continue  # Next poll will check for COMPLETED/FAILED from agent callback

        # ── Check if agent already reported back COMPLETED / FAILED ──────────
        # The agent calls POST /api/v1/agents/actions/{id}/result which sets
        # action.status = COMPLETED/FAILED. We just need to clean up the Redis flag.
        if action.status in (AgentActionStatus.COMPLETED, AgentActionStatus.FAILED):
            if redis:
                try:
                    redis.delete(install_key)
                    # Invalidate detection cache so the next poll reflects real state
                    redis.delete(f"spot:keda_detection:{cluster_id}")
                except Exception:
                    pass
            logger.info(
                f"[keda_installer] Action {action.id} ({action_type}) "
                f"{action.status.value} for cluster {cluster_id} — flag cleared"
            )


# ── W7.8: Stale autoscaler freeze cleanup ─────────────────────────────────────

@app.task(name="workers.keda.cleanup_stale_autoscaler_freezes", bind=True, max_retries=3)
def cleanup_stale_autoscaler_freezes(self):
    """
    W7.8 — Runs every 5 minutes (registered in app.py beat schedule).

    Scans all Redis keys matching spot:autoscaler_freeze:* and calls
    restore_autoscaler() for any freeze that:
      - Exists but has a frozen_at timestamp older than 180 seconds
      - OR has no frozen_at (legacy / corrupted entry) and key is > 180s old

    This is the safety net for crashed workers that called freeze_autoscaler()
    but never reached the finally block to call restore_autoscaler().
    """
    redis = get_redis_client()
    if not redis:
        logger.warning("[stale_freeze_cleanup] Redis not available — skipping")
        return {"cleaned": 0, "skipped": 0}

    db = next(get_db())
    cleaned = 0
    skipped = 0

    try:
        from backend.pipeline.stage4_decision.eviction_safety import restore_autoscaler
        from backend.models.cluster import Cluster

        # Scan all freeze keys — pattern: spot:autoscaler_freeze:{ns}/{ctrl}
        # Note: these keys intentionally don't include cluster_id in the key
        # (they rely on the cluster context passed at restore time).
        _cursor = 0
        _FREEZE_MAX_AGE_S = 180  # matches W7 TTL

        while True:
            _cursor, keys = redis.scan(
                cursor=_cursor,
                match="spot:autoscaler_freeze:*",
                count=100,
            )
            for key in keys:
                try:
                    _key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    _raw = redis.get(_key_str)
                    if not _raw:
                        continue  # Already expired — TTL cleared it

                    _freeze_data = json.loads(_raw)
                    _frozen_at_str = _freeze_data.get("frozen_at")
                    _ns = _freeze_data.get("namespace")
                    _ctrl = _freeze_data.get("controller_name")
                    _cid = _freeze_data.get("cluster_id", "")

                    if not _ns or not _ctrl:
                        # Malformed key — delete it
                        redis.delete(_key_str)
                        logger.warning(
                            f"[stale_freeze_cleanup] Deleted malformed freeze key: {_key_str}"
                        )
                        continue

                    # Compute age
                    if _frozen_at_str:
                        try:
                            _frozen_at = datetime.fromisoformat(_frozen_at_str)
                            _age_s = (datetime.utcnow() - _frozen_at).total_seconds()
                        except (ValueError, TypeError):
                            _age_s = _FREEZE_MAX_AGE_S + 1  # assume stale
                    else:
                        # No timestamp — treat as stale
                        _age_s = _FREEZE_MAX_AGE_S + 1

                    if _age_s < _FREEZE_MAX_AGE_S:
                        skipped += 1
                        continue

                    # Stale freeze detected — attempt restore
                    logger.warning(
                        f"[stale_freeze_cleanup] Stale freeze found: "
                        f"{_ns}/{_ctrl} (cluster={_cid}, age={_age_s:.0f}s) — restoring"
                    )

                    # Look up cluster for K8s + KEDA clients
                    if _cid:
                        cluster = db.query(Cluster).filter(Cluster.id == _cid).first()
                        if cluster:
                            try:
                                from backend.services.keda_service import KedaService
                                from kubernetes import client as _k8s
                                _keda_svc = KedaService(db=db, redis=redis)
                                _k8s_api  = _keda_svc._get_k8s_client(cluster)
                                _apps_v1  = _k8s.AppsV1Api(_k8s_api)

                                ok = restore_autoscaler(
                                    apps_v1=_apps_v1,
                                    keda_service=_keda_svc,
                                    namespace=_ns,
                                    controller_name=_ctrl,
                                    redis_client=redis,
                                    cluster_id=_cid,
                                )
                                if ok:
                                    cleaned += 1
                                    logger.info(
                                        f"[stale_freeze_cleanup] Restored {_ns}/{_ctrl} "
                                        f"(cluster={_cid})"
                                    )
                                else:
                                    # restore_autoscaler returned False — still remove the key
                                    redis.delete(_key_str)
                                    cleaned += 1
                                    logger.warning(
                                        f"[stale_freeze_cleanup] restore_autoscaler() returned "
                                        f"False for {_ns}/{_ctrl} — key deleted"
                                    )
                            except Exception as _restore_err:
                                logger.error(
                                    f"[stale_freeze_cleanup] restore failed for "
                                    f"{_ns}/{_ctrl}: {_restore_err}"
                                )
                                # Delete stale key regardless so it doesn't block permanently
                                redis.delete(_key_str)
                                cleaned += 1
                        else:
                            # Cluster not found — orphaned freeze key from deleted cluster
                            redis.delete(_key_str)
                            cleaned += 1
                            logger.warning(
                                f"[stale_freeze_cleanup] Deleted orphaned freeze key "
                                f"for unknown cluster {_cid}: {_key_str}"
                            )
                    else:
                        # No cluster_id in freeze data — delete key
                        redis.delete(_key_str)
                        cleaned += 1
                        logger.warning(
                            f"[stale_freeze_cleanup] Deleted freeze key with no "
                            f"cluster_id: {_key_str}"
                        )

                except Exception as _key_err:
                    logger.error(
                        f"[stale_freeze_cleanup] Error processing key {key}: {_key_err}"
                    )

            if _cursor == 0:
                break

        if cleaned > 0:
            logger.info(
                f"[stale_freeze_cleanup] Complete: {cleaned} stale freeze(s) cleaned, "
                f"{skipped} active freeze(s) skipped"
            )

        return {"cleaned": cleaned, "skipped": skipped}

    except Exception as exc:
        logger.error(f"[stale_freeze_cleanup] Top-level error: {exc}", exc_info=True)
        return {"cleaned": cleaned, "skipped": skipped, "error": str(exc)}
    finally:
        db.close()
