"""
validate_actions_task — Real-time EVICT_POD convergence validator

Runs every 15 seconds via Celery beat.

For each PENDING/PICKED_UP EVICT_POD action:
  - Deadline check (always runs, not gated by freshness):
      If deadline has passed without convergence → mark FAILED (deadline_exceeded)
  - Freshness gate (C5 fix):
      Read spot:workload:state:{cluster_id}:{workload_id} updated_at.
      If state data is older than VALIDATOR_MAX_DATA_AGE_SECS → skip convergence check
      this cycle and log stale_data_defer.  The action is NOT failed — it will be
      retried on the next cycle when fresh data arrives.
  - Convergence check (only runs when data is fresh):
      Read spot:workload:pods:{cluster_id}:{workload_id}.
      If pod is present on a DIFFERENT node → converged → mark COMPLETED, observed=True.

Convergence definition (EVICT_POD):
  pod.node != expected.from_node
  (pod moved off the node it was on when the eviction was dispatched)

C5 — Why updated_at from spot:workload:state as proxy:
  The agent writes BOTH spot:workload:state and spot:workload:pods on the same
  heartbeat cycle.  If updated_at is stale, pods data is equally stale.
  We cannot call the K8s API directly from the backend — only the agent has
  in-cluster credentials.  Using the state key's updated_at is the authoritative
  freshness signal available without an extra network hop.
"""
import json
import logging
import os
import time
from datetime import datetime

from celery import shared_task
from sqlalchemy.orm import Session

from backend.models.base import SessionLocal
from backend.models.agent_action import AgentAction, AgentActionStatus, AgentActionType

logger = logging.getLogger(__name__)

# Maximum age (seconds) of spot:workload:state updated_at before we consider the
# observation layer too stale to make a convergence judgement.
# Default 60 s — twice the normal agent heartbeat cadence — gives one missed
# heartbeat before we defer.  Override with VALIDATOR_MAX_DATA_AGE_SECS env var.
VALIDATOR_MAX_DATA_AGE_SECS: int = int(os.getenv("VALIDATOR_MAX_DATA_AGE_SECS", "60"))


@shared_task(name="validate_eviction_actions", bind=True, max_retries=0)
def validate_eviction_actions(self):
    """
    Checks in-flight EVICT_POD actions for convergence or deadline expiry.
    Runs every 15 s; must be fast (reads only Redis + one DB query).
    """
    db: Session = SessionLocal()
    try:
        _run_validation(db)
    except Exception as exc:
        logger.error("[VALIDATOR] unhandled error: %s", exc, exc_info=True)
    finally:
        db.close()


def _check_state_freshness(r, cluster_id: str, workload_id: str, now: float) -> tuple[bool, float]:
    """
    C5: Check whether the agent's observation data is fresh enough to trust.

    Reads spot:workload:state:{cluster_id}:{workload_id} and inspects updated_at.
    Returns (is_fresh: bool, data_age_seconds: float).

    If the state key is absent we treat the data as stale (unknown freshness).
    Both spot:workload:state and spot:workload:pods are written by the same agent
    heartbeat, so a stale state key implies stale pods data.
    """
    try:
        state_raw = r.get(f"spot:workload:state:{cluster_id}:{workload_id}")
        if state_raw is None:
            return False, float("inf")
        state = json.loads(state_raw)
        updated_at = state.get("updated_at")
        if updated_at is None:
            return False, float("inf")
        age = now - float(updated_at)
        return age <= VALIDATOR_MAX_DATA_AGE_SECS, age
    except Exception as e:
        logger.debug("[VALIDATOR] freshness check error for %s/%s: %s", cluster_id, workload_id, e)
        return False, float("inf")


def _run_validation(db: Session) -> None:
    from backend.core.config import settings
    import redis as redis_lib

    active_actions = (
        db.query(AgentAction)
        .filter(
            AgentAction.action_type == AgentActionType.EVICT_POD,
            AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
        )
        .limit(200)
        .all()
    )

    if not active_actions:
        return

    try:
        _r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as re:
        logger.warning("[VALIDATOR] Redis unavailable: %s — skipping cycle", re)
        return

    now = time.time()
    changed = 0

    for action in active_actions:
        result = action.result or {}
        expected = result.get("expected")
        deadline = result.get("deadline")

        if not expected:
            # Action predates convergence tracking — skip
            continue

        pod_name = expected.get("pod_name")
        from_node = expected.get("from_node")
        workload_id = expected.get("workload_id") or (action.payload or {}).get("workload_id", "")

        # ── 1. Deadline check — always runs, NOT gated by freshness ───────────
        # Even if the observation layer is stale, a timed-out action must be
        # expired. False positives here are preferable to actions that never
        # reach a terminal state.
        if deadline and now > float(deadline):
            action.status = AgentActionStatus.FAILED
            action.result = {
                **result,
                "failure_reason": "deadline_exceeded",
                "failed_at": now,
            }
            logger.warning(
                "[VALIDATOR] FAILED(timeout) action=%s pod=%s cluster=%s",
                action.id, pod_name, action.cluster_id,
            )
            changed += 1
            continue

        # ── 2. Freshness gate (C5) — defer convergence if data is stale ───────
        # The agent writes both spot:workload:state and spot:workload:pods on the
        # same heartbeat.  If state.updated_at is too old, the pods list is also
        # stale — trusting it could produce false timeouts or false confirmations.
        # Action: skip this cycle and retry on the next 15 s tick.
        if not pod_name or not from_node:
            continue

        is_fresh, data_age = _check_state_freshness(_r, action.cluster_id, workload_id, now)
        if not is_fresh:
            logger.warning(
                "[VALIDATOR] stale_data_defer action=%s pod=%s cluster=%s "
                "data_age=%.1fs threshold=%ds — deferring convergence check",
                action.id, pod_name, action.cluster_id,
                data_age if data_age != float("inf") else -1,
                VALIDATOR_MAX_DATA_AGE_SECS,
            )
            # Record the defer in the action result so the UI can surface it
            action.result = {
                **result,
                "last_stale_defer_at": now,
                "last_data_age_secs": round(data_age, 1) if data_age != float("inf") else None,
            }
            changed += 1
            continue

        # ── 3. Convergence check — only when observation data is fresh ─────────
        pods_key = f"spot:workload:pods:{action.cluster_id}:{workload_id}"
        try:
            pods_raw = _r.get(pods_key)
            if pods_raw is None:
                continue
            pods_data = json.loads(pods_raw)
        except Exception:
            continue

        # Find the pod in the current pod list
        current_node: str | None = None
        pod_found = False
        for p in pods_data:
            if p.get("name") == pod_name:
                pod_found = True
                current_node = p.get("node")
                break

        if pod_found and current_node and current_node != from_node:
            # Pod is alive on a different node — eviction + reschedule confirmed
            action.status = AgentActionStatus.COMPLETED
            action.completed_at = datetime.utcnow()
            action.result = {
                **result,
                "observed": True,
                "verified_at": now,
                "landed_on_node": current_node,
                "data_age_at_verification_secs": round(data_age, 1),
            }
            logger.info(
                "[VALIDATOR] VERIFIED action=%s pod=%s moved %s → %s (data_age=%.1fs)",
                action.id, pod_name, from_node, current_node, data_age,
            )
            changed += 1

    if changed:
        db.commit()
        logger.debug("[VALIDATOR] committed %d action updates", changed)
