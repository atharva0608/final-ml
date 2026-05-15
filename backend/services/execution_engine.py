"""
Execution Engine — Manifest-driven cluster execution orchestrator.
==================================================================

Consumes an ExecutionManifest produced by DistributionEngine and drives
every real cluster action: node provisioning, pod eviction, node drain,
node termination, and post-execution verification.

Pipeline (strict execution order):
    ManifestStore        → read/write/expire manifests in Redis
    ActionTracker        → write-ahead log for crash recovery
    ExecutionGate        → 10 Redis checks, zero cluster contact
    RaceGuard            → compare precondition snapshot vs WIE cache
    NodeProvisioner      → provision / reuse nodes via KarpenterService
    StatefulExecutor     → BLUE_GREEN groups, sequential, state-machine per pod
    StatelessExecutor    → BATCH groups, parallel across groups
    Verifier             → post-execution WIE cache comparison
    FeedbackHandler      → classify mismatches, set scoped replan signals
    ExecutionEngine      → orchestrator, owns cluster state transitions

Design rules:
- No K8s API calls during execution except via AgentAction DB dispatch.
- All live data reads from WIE Redis cache — never direct K8s calls.
- Every real action is preceded by an ActionTracker.start() write.
- The finally block in ExecutionEngine ALWAYS resets cluster state to IDLE.
- Settings always loaded live from DB at EE startup — never cached.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MANIFEST_TTL_SECONDS = 3600  # DB-primary TTL; Redis cache mirrors with shorter TTL
MANIFEST_REDIS_TTL   = 120   # Redis key TTL — fast-read cache only


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _get_redis():
    from backend.core.redis_client import get_redis_client
    return get_redis_client()


def _decode(raw) -> str:
    if raw is None:
        return ""
    return raw.decode() if isinstance(raw, bytes) else str(raw)


# ---------------------------------------------------------------------------
# WIE Cache Helpers
# (All cluster reads go through these — no direct K8s API calls)
# ---------------------------------------------------------------------------

def _read_wie_pod_state(cluster_id: str, pod_name: str) -> Optional[Dict]:
    r = _get_redis()
    if not r:
        return None
    raw = r.get(f"spot:wie:pod_state:{cluster_id}:{pod_name}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _read_wie_node_state(cluster_id: str, node_name: str) -> Optional[Dict]:
    r = _get_redis()
    if not r:
        return None
    raw = r.get(f"spot:wie:node_state:{cluster_id}:{node_name}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _read_wie_az_capacity(cluster_id: str, az: str) -> Optional[float]:
    r = _get_redis()
    if not r:
        return None
    raw = r.get(f"spot:wie:az_capacity:{cluster_id}:{az}")
    try:
        return float(raw) if raw else None
    except Exception:
        return None


def _read_wie_node_pod_count(cluster_id: str, node_name: str) -> Optional[int]:
    r = _get_redis()
    if not r:
        return None
    raw = r.get(f"spot:cluster:node_pod_count:{cluster_id}:{node_name}")
    try:
        return int(raw) if raw else None
    except Exception:
        return None


def _read_wie_draining_nodes(cluster_id: str) -> List[Dict]:
    r = _get_redis()
    if not r:
        return []
    raw = r.get(f"spot:wie:draining_nodes:{cluster_id}")
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _read_wie_all_nodes(cluster_id: str) -> List[Dict]:
    r = _get_redis()
    if not r:
        return []
    raw = r.get(f"spot:cluster:spot_nodes:{cluster_id}")
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _lookup_instance_price(instance_type: str, capacity_type: str) -> float:
    try:
        from backend.core.redis_client import get_redis_client
        _r = get_redis_client()
        key = f"spot:pricing:{instance_type}:{capacity_type}"
        raw = _r.get(key) if _r else None
        return float(raw) if raw else 0.0
    except Exception:
        return 0.0


def _lookup_pvc_az(db, pod_name: str) -> Optional[str]:
    try:
        from backend.models.node_metadata import NodeMetadata
        row = db.query(NodeMetadata).filter(
            NodeMetadata.pod_name == pod_name
        ).first()
        return getattr(row, "az", None) if row else None
    except Exception:
        return None


def _extract_ordinal(pod_name: str) -> int:
    parts = pod_name.rsplit("-", 1)
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def _collect_all_steps(manifest: Dict) -> List[Dict]:
    steps = []
    for group in manifest.get("migration_groups", []):
        gtype = group.get("type", "")
        if gtype == "BLUE_GREEN":
            steps.extend(group.get("steps", []))
        elif gtype == "BATCH":
            for batch in group.get("batches", []):
                steps.extend(batch.get("steps", []))
    return steps


def _wait_pod_running(
    cluster_id: str, pod_name: str, target_node: str,
    timeout: int = 120, poll_interval: int = 10,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _read_wie_pod_state(cluster_id, pod_name)
        if state:
            on_target = state.get("node_name") == target_node
            running = state.get("phase") in ("Running", "Succeeded")
            if on_target and running:
                return True
        time.sleep(poll_interval)
    return False


def _pod_still_healthy(cluster_id: str, pod_name: str, target_node: str) -> bool:
    state = _read_wie_pod_state(cluster_id, pod_name)
    if not state:
        return True  # can't verify — optimistic
    return (
        state.get("node_name") == target_node
        and state.get("phase") in ("Running", "Succeeded")
    )


def _patch_affinity(cluster_id: str, pod_name: str, namespace: str, target_node: str, db) -> str:
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.PATCH_AFFINITY,
        status=AgentActionStatus.PENDING,
        payload={
            "pod_name": pod_name,
            "namespace": namespace,
            "node_name": target_node,
            "source": "execution_engine",
        },
    )
    db.add(action)
    db.commit()
    return action.id


def _evict_pod_action(cluster_id: str, pod_name: str, namespace: str, node_name: str, db) -> str:
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.EVICT_POD,
        status=AgentActionStatus.PENDING,
        payload={
            "pod_name": pod_name,
            "namespace": namespace,
            "node_name": node_name,
            "source": "execution_engine",
        },
    )
    db.add(action)
    db.commit()
    return action.id


def _shift_traffic(cluster_id: str, pod_name: str, namespace: str, mechanism: str, step: Dict, db) -> bool:
    """Dispatch traffic-shift AgentAction based on mechanism from manifest."""
    try:
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        if mechanism == "service_selector_patch":
            action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.PATCH_AFFINITY,
                status=AgentActionStatus.PENDING,
                payload={
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "source": "execution_engine:traffic_shift",
                    "mechanism": mechanism,
                    "workload_id": step.get("workload_id"),
                },
            )
            db.add(action)
            db.commit()
        # Other mechanisms (sentinel_promotion, connection_pool_reroute, cluster_rebalance)
        # are handled by the agent via ANNOTATE_WORKLOAD — emit annotation action
        elif mechanism in ("sentinel_promotion", "connection_pool_reroute", "cluster_rebalance"):
            action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.ANNOTATE_WORKLOAD,
                status=AgentActionStatus.PENDING,
                payload={
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "annotation": f"spot-optimizer.io/traffic-shift={mechanism}",
                    "source": "execution_engine:traffic_shift",
                },
            )
            db.add(action)
            db.commit()
        return True
    except Exception as exc:
        logger.error(f"[EE] _shift_traffic failed: {exc}")
        return False


def _execute_rollback(cluster_id: str, rollback_map: Dict, pod_name: str, namespace: str, db) -> None:
    mechanism = rollback_map.get("mechanism", "service_selector_patch")
    logger.warning(f"[EE] executing rollback for pod={pod_name} mechanism={mechanism}")
    try:
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.ANNOTATE_WORKLOAD,
            status=AgentActionStatus.PENDING,
            payload={
                "pod_name": pod_name,
                "namespace": namespace,
                "annotation": "spot-optimizer.io/rollback=true",
                "source": "execution_engine:rollback",
                "mechanism": mechanism,
            },
        )
        db.add(action)
        db.commit()
    except Exception as exc:
        logger.error(f"[EE] rollback dispatch failed for pod={pod_name}: {exc}")


def _pdb_safe_to_drain(node_name: str, db) -> bool:
    """Conservative PDB check — if we can't verify, allow drain."""
    try:
        from backend.models.pod_metric import PodMetric
        pods_on_node = db.query(PodMetric).filter(
            PodMetric.node_name == node_name
        ).all()
        for pod in pods_on_node:
            workload_id = getattr(pod, "workload_id", None)
            if not workload_id:
                continue
            pdb_min = getattr(pod, "pdb_min_available", None)
            ready = getattr(pod, "ready_replicas", None)
            if pdb_min is not None and ready is not None:
                if (ready - 1) < pdb_min:
                    logger.warning(f"[EE] PDB check: draining {node_name} would violate {workload_id} pdb_min={pdb_min}")
                    return False
        return True
    except Exception as exc:
        logger.debug(f"[EE] _pdb_safe_to_drain error — allowing drain: {exc}")
        return True


def _increment_circuit_breaker(cluster_id: str, window_seconds: int = 600) -> None:
    r = _get_redis()
    if not r:
        return
    key = f"spot:exec_fail_window:{cluster_id}"
    r.incr(key)
    r.expire(key, window_seconds)


def _signal_replan(cluster_id: str, reason: str) -> None:
    r = _get_redis()
    if r:
        r.setex(f"spot:ee:replan_needed:{cluster_id}", 600, reason)
    logger.info(f"[EE] Replan signalled: cluster={cluster_id} reason={reason}")


# ---------------------------------------------------------------------------
# Layer 1 — ManifestStore
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# EE Exception hierarchy
# ---------------------------------------------------------------------------

class EEError(Exception):
    """Base for all ExecutionEngine errors."""


class ApprovalRequiredError(EEError):
    """Failover requires human approval."""


class ReplanRequiredError(EEError):
    """
    Problem 13 — mid-run split triggered during NodeProvisioner retry.
    EE aborts the group and signals replanning.
    """
    def __init__(self, msg: str, original_entry: Optional[Dict] = None,
                 split_entries: Optional[List[Dict]] = None):
        super().__init__(msg)
        self.original_entry = original_entry
        self.split_entries  = split_entries or []


# ---------------------------------------------------------------------------
# Layer 1 — ManifestStore  (DB-primary + Redis cache, Problem 2)
# ---------------------------------------------------------------------------

class ManifestStore:
    """
    DB-primary manifest store (Problems 2, 3, 22, 29).
    Redis is a fast-read cache only — DB row is source of truth.
    Survives Redis evictions and restarts.
    """

    KEY_PREFIX   = "spot:ee:manifest"
    REDIS_TTL    = MANIFEST_REDIS_TTL
    VALID_STATUSES = frozenset({"READY", "EXECUTING"})

    @staticmethod
    def write(cluster_id: str, manifest: Dict,
              ttl: int = MANIFEST_TTL_SECONDS, db=None) -> None:
        """Write manifest.  DB-primary; Redis is cache."""
        if db is not None:
            ManifestStore._write_db(cluster_id, manifest, ttl, db)
        r = _get_redis()
        if r:
            try:
                r.setex(
                    f"{ManifestStore.KEY_PREFIX}:{cluster_id}",
                    ManifestStore.REDIS_TTL,
                    json.dumps(manifest),
                )
            except Exception as _re:
                logger.debug("[ManifestStore] Redis write failed (non-fatal): %s", _re)

    @staticmethod
    def _write_db(cluster_id: str, manifest: Dict, ttl: int, db) -> None:
        try:
            from datetime import timedelta
            from backend.models.execution_manifest import ExecutionManifest
            manifest_id = manifest.get("manifest_id")
            if not manifest_id:
                return
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            row = db.query(ExecutionManifest).filter(
                ExecutionManifest.manifest_id == manifest_id
            ).first()
            if row:
                row.payload    = manifest
                row.status     = "READY"
                row.expires_at = expires_at
                row.updated_at = datetime.now(timezone.utc)
            else:
                row = ExecutionManifest(
                    manifest_id = manifest_id,
                    cluster_id  = cluster_id,
                    status      = "READY",
                    payload     = manifest,
                    expires_at  = expires_at,
                    created_at  = datetime.now(timezone.utc),
                    updated_at  = datetime.now(timezone.utc),
                )
                db.add(row)
            db.commit()
        except Exception as e:
            logger.warning("[ManifestStore] DB write failed: %s", e)
            try:
                db.rollback()
            except Exception:
                pass

    @staticmethod
    def read(cluster_id: str, db=None) -> Optional[Dict]:
        """Read manifest.  Redis fast-path; DB fallback."""
        r = _get_redis()
        if r:
            try:
                raw = r.get(f"{ManifestStore.KEY_PREFIX}:{cluster_id}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        if db is not None:
            return ManifestStore._read_db_latest(cluster_id, db)
        return None

    @staticmethod
    def _read_db_latest(cluster_id: str, db) -> Optional[Dict]:
        try:
            from backend.models.execution_manifest import ExecutionManifest
            row = db.query(ExecutionManifest).filter(
                ExecutionManifest.cluster_id == cluster_id,
                ExecutionManifest.status.in_(["READY", "EXECUTING"]),
            ).order_by(ExecutionManifest.created_at.desc()).first()
            return row.payload if row else None
        except Exception as e:
            logger.debug("[ManifestStore] DB read failed: %s", e)
            return None

    @staticmethod
    def transition(manifest_id: str, new_status: str, db, redis=None) -> None:
        """
        Problem 22 — acquires blocking FOR UPDATE lock before writing.
        Shared lock semantics with EE._manifest_still_valid().
        Problem 29 — callers must operate under READ COMMITTED isolation.
        """
        try:
            from sqlalchemy import text
            from backend.models.execution_manifest import ExecutionManifest
            db.execute(text(
                "SET LOCAL TRANSACTION ISOLATION LEVEL READ COMMITTED"
            ))
            row = db.query(ExecutionManifest).filter(
                ExecutionManifest.manifest_id == manifest_id
            ).with_for_update().first()  # blocking — NOT skip_locked (Problem 22)
            if not row:
                return
            if row.status in ("COMPLETED", "FAILED", "EXPIRED"):
                return  # already terminal — another worker transitioned it
            row.status     = new_status
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            if redis:
                try:
                    redis.setex(
                        f"{ManifestStore.KEY_PREFIX}:status:{manifest_id}",
                        ManifestStore.REDIS_TTL,
                        new_status,
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error("[ManifestStore] transition failed: %s", e)
            try:
                db.rollback()
            except Exception:
                pass

    @staticmethod
    def heartbeat(manifest_id: str, db) -> None:
        """Update last_heartbeat.  TTLMonitor uses this to detect stale manifests."""
        try:
            from backend.models.execution_manifest import ExecutionManifest
            row = db.query(ExecutionManifest).filter(
                ExecutionManifest.manifest_id == manifest_id
            ).first()
            if row:
                row.last_heartbeat = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.debug("[ManifestStore] heartbeat failed: %s", e)

    @staticmethod
    def read_with_overrides(cluster_id: str, db) -> Optional[Dict]:
        """
        GAP 3 — UI read layer that merges latest ExecutionOverride rows onto
        manifest node_plan so the UI always sees the actual (current) instance_type.

        merge contract:
          manifest.node_plan entry  →  merge({node_name fields}, latest override for that node)
          only fields present in ExecutionOverride rows are overwritten
          manifest payload itself is NEVER mutated (returns a new dict)

        returns:
          None                      — no READY/EXECUTING manifest for cluster
          merged manifest dict      — payload with node_plan entries updated
        """
        manifest = ManifestStore.read(cluster_id, db=db)
        if not manifest:
            return None

        manifest_id = manifest.get("manifest_id")
        if not manifest_id or db is None:
            return manifest

        try:
            overrides = ExecutionOverrideStore.read_all(manifest_id, db)
            if not overrides:
                return manifest

            raw_node_plan = manifest.get("node_plan") or []
            merged_node_plan = ExecutionOverrideStore.apply(raw_node_plan, overrides)

            # Return a shallow copy of manifest with merged node_plan only
            return {**manifest, "node_plan": merged_node_plan, "_overrides_applied": True}

        except Exception as e:
            logger.debug("[ManifestStore] read_with_overrides merge failed (using raw): %s", e)
            return manifest

    @staticmethod
    def delete(cluster_id: str) -> None:
        r = _get_redis()
        if r:
            r.delete(f"{ManifestStore.KEY_PREFIX}:{cluster_id}")


# ---------------------------------------------------------------------------
# ExecutionOverrideStore  (Problems 16, 17, 26)
# ---------------------------------------------------------------------------

class ExecutionOverrideStore:
    """
    Append-only mid-run field override log.
    NodeProvisioner writes here instead of mutating the manifest payload.
    EE reads and merges overrides at resume time and before each group.
    Problem 26 — append-only: each attempt inserts a new row.
    """

    @staticmethod
    def write(
        manifest_id: str,
        node_name: str,
        field: str,
        original_value: Optional[str],
        override_value: str,
        reason: str,
        db,
    ) -> None:
        """Append a new override row.  Never upserts (Problem 26)."""
        try:
            from backend.models.execution_override import ExecutionOverride
            prev_max = db.query(
                ExecutionOverride
            ).filter(
                ExecutionOverride.manifest_id == manifest_id,
                ExecutionOverride.node_name   == node_name,
                ExecutionOverride.field        == field,
            ).count()
            row = ExecutionOverride(
                manifest_id    = manifest_id,
                node_name      = node_name,
                field          = field,
                original_value = original_value,
                override_value = override_value,
                reason         = reason,
                attempt_number = prev_max,   # 0-indexed count of prior rows
                created_at     = datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
        except Exception as e:
            logger.error("[ExecutionOverrideStore] write failed: %s", e)
            try:
                db.rollback()
            except Exception:
                pass

    @staticmethod
    def read_all(manifest_id: str, db) -> Dict[str, Dict]:
        """
        Returns {node_name: {field: latest_override_value, ...}, ...}.
        Used by EE at resume time and before each group.
        """
        result: Dict[str, Dict] = {}
        try:
            from backend.models.execution_override import ExecutionOverride
            rows = db.query(ExecutionOverride).filter(
                ExecutionOverride.manifest_id == manifest_id,
            ).order_by(
                ExecutionOverride.attempt_number.asc()
            ).all()
            for row in rows:
                if row.node_name not in result:
                    result[row.node_name] = {}
                result[row.node_name][row.field] = row.override_value
        except Exception as e:
            logger.debug("[ExecutionOverrideStore] read_all failed: %s", e)
        return result

    @staticmethod
    def read_history(manifest_id: str, node_name: str, db) -> List[Dict]:
        """Full audit log for (manifest_id, node_name) — all attempts."""
        try:
            from backend.models.execution_override import ExecutionOverride
            rows = db.query(ExecutionOverride).filter(
                ExecutionOverride.manifest_id == manifest_id,
                ExecutionOverride.node_name   == node_name,
            ).order_by(
                ExecutionOverride.attempt_number.asc()
            ).all()
            return [
                {
                    "field":          r.field,
                    "original_value": r.original_value,
                    "override_value": r.override_value,
                    "reason":         r.reason,
                    "attempt_number": r.attempt_number,
                    "created_at":     r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug("[ExecutionOverrideStore] read_history failed: %s", e)
            return []

    @staticmethod
    def apply(manifest_entries: List[Dict], overrides: Dict[str, Dict]) -> List[Dict]:
        """Merge overrides onto manifest entries (non-destructive — returns new list)."""
        result = []
        for entry in manifest_entries:
            node_name = entry.get("node_name")
            if node_name and node_name in overrides:
                result.append({**entry, **overrides[node_name]})
            else:
                result.append(entry)
        return result


# ---------------------------------------------------------------------------
# TTLMonitor  (Problems 3, 22, 29)
# ---------------------------------------------------------------------------

class TTLMonitor:
    """
    Expires stale EXECUTING manifests at phase boundaries.
    Uses blocking with_for_update() to share lock semantics with EE (Problem 22).
    Operates under READ COMMITTED isolation (Problem 29).
    """

    GRACE_SECONDS = 60  # allow EE this long after last heartbeat before expiry

    @staticmethod
    def check_and_expire(db, redis=None) -> List[str]:
        """
        1. SELECT manifests in EXECUTING with last_heartbeat stale > GRACE_SECONDS.
        2. For each: acquire FOR UPDATE lock, re-check status, transition to EXPIRED.
        3. Returns list of expired manifest_ids.
        """
        expired_ids: List[str] = []
        try:
            from sqlalchemy import text
            from backend.models.execution_manifest import ExecutionManifest
            from datetime import timedelta

            db.execute(text(
                "SET LOCAL TRANSACTION ISOLATION LEVEL READ COMMITTED"
            ))

            cutoff = datetime.now(timezone.utc) - timedelta(seconds=TTLMonitor.GRACE_SECONDS)
            candidates = db.query(ExecutionManifest).filter(
                ExecutionManifest.status == "EXECUTING",
                ExecutionManifest.last_heartbeat < cutoff,
            ).all()

            for row in candidates:
                try:
                    locked_row = db.query(ExecutionManifest).filter(
                        ExecutionManifest.manifest_id == row.manifest_id
                    ).with_for_update().first()  # blocking (Problem 22)
                    if not locked_row:
                        continue
                    if locked_row.status in ("COMPLETED", "FAILED", "EXPIRED", "READY"):
                        continue  # another worker already handled it
                    locked_row.status     = "EXPIRED"
                    locked_row.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    expired_ids.append(row.manifest_id)
                    logger.info(
                        "[TTLMonitor] manifest_expired manifest_id=%s cluster_id=%s",
                        row.manifest_id, row.cluster_id,
                    )
                except Exception as _inner:
                    logger.warning("[TTLMonitor] row error manifest_id=%s: %s",
                                   row.manifest_id, _inner)
                    try:
                        db.rollback()
                    except Exception:
                        pass
        except Exception as e:
            logger.error("[TTLMonitor] check_and_expire failed: %s", e)
        return expired_ids


# ---------------------------------------------------------------------------
# Layer 2 — ActionTracker
# ---------------------------------------------------------------------------

class ActionTracker:
    """
    Write-ahead log. Written BEFORE touching the cluster.
    On crash/restart, get_all() shows IN_PROGRESS entries for recovery.
    """

    KEY_PREFIX = "spot:ee:action"
    TTL = 3600

    @staticmethod
    def start(
        cluster_id: str, execution_id: str, pod_name: str,
        action: str, from_node: Optional[str], to_node: Optional[str],
    ) -> None:
        r = _get_redis()
        if not r:
            return
        key = f"{ActionTracker.KEY_PREFIX}:{cluster_id}:{execution_id}:{pod_name}"
        r.hset(key, mapping={
            "pod_name":        pod_name,
            "action":          action,
            "status":          "IN_PROGRESS",
            "from_node":       from_node or "",
            "to_node":         to_node or "",
            "started_at":      _utc_now_iso(),
            "completed_at":    "",
            "error":           "",
            "agent_action_ids": "[]",
        })
        r.expire(key, ActionTracker.TTL)

    @staticmethod
    def complete(cluster_id: str, execution_id: str, pod_name: str) -> None:
        r = _get_redis()
        if not r:
            return
        key = f"{ActionTracker.KEY_PREFIX}:{cluster_id}:{execution_id}:{pod_name}"
        r.hset(key, mapping={"status": "COMPLETED", "completed_at": _utc_now_iso()})

    @staticmethod
    def fail(cluster_id: str, execution_id: str, pod_name: str, error: str) -> None:
        r = _get_redis()
        if not r:
            return
        key = f"{ActionTracker.KEY_PREFIX}:{cluster_id}:{execution_id}:{pod_name}"
        r.hset(key, mapping={
            "status":       "FAILED",
            "completed_at": _utc_now_iso(),
            "error":        error[:512],
        })

    @staticmethod
    def add_agent_action(
        cluster_id: str, execution_id: str, pod_name: str, agent_action_id: str,
    ) -> None:
        r = _get_redis()
        if not r:
            return
        key = f"{ActionTracker.KEY_PREFIX}:{cluster_id}:{execution_id}:{pod_name}"
        raw = r.hget(key, "agent_action_ids")
        ids: List[str] = json.loads(raw or "[]")
        ids.append(str(agent_action_id))
        r.hset(key, "agent_action_ids", json.dumps(ids))

    @staticmethod
    def get_all(cluster_id: str, execution_id: str) -> List[Dict[str, str]]:
        r = _get_redis()
        if not r:
            return []
        pattern = f"{ActionTracker.KEY_PREFIX}:{cluster_id}:{execution_id}:*"
        keys = r.keys(pattern)
        result = []
        for k in keys:
            raw = r.hgetall(k)
            result.append({
                _decode(fk): _decode(fv) for fk, fv in raw.items()
            })
        return result


# ---------------------------------------------------------------------------
# Layer 3 — ExecutionGate
# ---------------------------------------------------------------------------

class ExecutionGate:
    """
    10 Redis checks. First failure exits with reason code.
    Zero cluster contact — pure Redis reads (Gate 10 is the one write).
    """

    @staticmethod
    def check(
        cluster_id: str,
        manifest: Dict,
        circuit_breaker_threshold: int = 10,
        post_execution_cooldown_seconds: int = 0,
    ) -> Tuple[bool, str]:
        r = _get_redis()
        if not r:
            return True, "no_redis_skip_gates"

        # Gate 1 — shadow mode
        if r.exists(f"spot:shadow_mode:{cluster_id}"):
            return False, "shadow_mode_active"

        # Gate 2 — post-execution cooldown (opt-in, default 0 = disabled)
        if post_execution_cooldown_seconds > 0:
            if r.exists(f"spot:ee:cooldown:{cluster_id}"):
                return False, "post_execution_cooldown"

        # Gate 3 — karpenter pause (cluster-scoped)
        if r.exists(f"spot:karpenter_pause:{cluster_id}"):
            return False, "karpenter_pause_active"

        # Gate 4 — circuit breaker
        fail_raw = r.get(f"spot:exec_fail_window:{cluster_id}")
        fail_count = int(fail_raw) if fail_raw else 0
        if fail_count >= circuit_breaker_threshold:
            return False, f"circuit_breaker_open:{fail_count}_failures"

        # Gate 5 — cluster mode must be "auto"
        mode_raw = r.get(f"spot:cluster:mode:{cluster_id}")
        if mode_raw:
            mode = _decode(mode_raw)
            if mode not in ("auto", ""):
                return False, f"cluster_mode_not_auto:{mode}"

        # Gate 6 — manifest TTL check
        generated_at = manifest.get("generated_at")
        if generated_at:
            try:
                gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                if gen_dt.tzinfo is None:
                    gen_dt = gen_dt.replace(tzinfo=timezone.utc)
                age = (_utc_now() - gen_dt).total_seconds()
                if age > MANIFEST_TTL_SECONDS:
                    return False, f"manifest_ttl_expired:{age:.0f}s"
            except Exception:
                pass

        # Gate 7 — cluster state must be IDLE
        state_raw = r.get(f"spot:cluster:state:{cluster_id}")
        if state_raw:
            state = _decode(state_raw)
            if state not in ("IDLE", ""):
                return False, f"cluster_state_not_idle:{state}"

        # Gate 8 — legacy rebalance lock
        if r.exists(f"spot:rebalance_lock:{cluster_id}"):
            return False, "rebalance_lock_held"

        # Gate 9 — Argo CD sync in progress
        if r.exists(f"spot:argocd_sync:{cluster_id}"):
            return False, "argocd_sync_in_progress"

        # Gate 10 — acquire execution lock (atomic NX, 300s TTL)
        execution_id = manifest.get("manifest_id") or str(uuid.uuid4())
        acquired = r.set(
            f"spot:ee:exec_lock:{cluster_id}",
            execution_id,
            nx=True,
            ex=300,
        )
        if not acquired:
            return False, "execution_lock_contention"

        return True, "all_gates_passed"


# ---------------------------------------------------------------------------
# Layer 4 — RaceGuard
# ---------------------------------------------------------------------------

class RaceGuard:
    """
    Compares DE's frozen precondition_snapshot against current WIE cache.
    Stale plan → abort + signal replan. Not an error — just a fresh cycle needed.
    """

    @staticmethod
    def check(cluster_id: str, manifest: Dict) -> Tuple[bool, str]:
        snapshot = manifest.get("precondition_snapshot", {})

        pod_positions = snapshot.get("pod_positions", {})
        target_nodes = snapshot.get("target_nodes", [])
        az_capacity = snapshot.get("az_capacity", {})

        # Check 1 — any pod already Pending (cluster already unstable)
        for pod_name in pod_positions:
            state = _read_wie_pod_state(cluster_id, pod_name)
            if state and state.get("phase") == "Pending":
                _signal_replan(cluster_id, f"pod_pending:{pod_name}")
                return False, f"pod_pending:{pod_name}"

        # Check 2 — pod positions haven't changed since planning
        for pod_name, expected_node in pod_positions.items():
            state = _read_wie_pod_state(cluster_id, pod_name)
            if state and state.get("node_name") != expected_node:
                _signal_replan(cluster_id, f"pod_moved:{pod_name}")
                return False, f"pod_position_changed:{pod_name}"

        # Check 3 — target nodes are Ready
        for node_name in target_nodes:
            state = _read_wie_node_state(cluster_id, node_name)
            if state and state.get("ready") is False:
                _signal_replan(cluster_id, f"target_node_not_ready:{node_name}")
                return False, f"target_node_not_ready:{node_name}"

        # Check 4 — AZ capacity hasn't degraded >20% since planning
        for az, snapped_cap in az_capacity.items():
            current = _read_wie_az_capacity(cluster_id, az)
            if current is not None and snapped_cap > 0:
                if current < snapped_cap * 0.8:
                    _signal_replan(cluster_id, f"az_capacity_degraded:{az}")
                    return False, f"az_capacity_degraded:{az}"

        return True, "preconditions_verified"


# ---------------------------------------------------------------------------
# Layer 5 — NodeProvisioner
# ---------------------------------------------------------------------------

class NodeProvisioner:
    """
    Reads already-resolved instance_type from manifest entry (set by InstanceSelectionService
    at planning time).  For mid-run pool failure only, accepts optional ISS injection.
    Uses ExecutionOverrideStore — never mutates manifest entries in-place (Problems 16, 17).
    Raises ReplanRequiredError on mid-run split (Problem 13).
    """

    def __init__(self, instance_selection_service=None):
        """Problem 11: ISS is optional — only for mid-run pool failure retry."""
        self.iss = instance_selection_service

    @staticmethod
    def provision_all(
        cluster_id: str,
        node_plan: List[Dict],
        max_nodes_per_cycle: int = 3,
        node_ready_timeout: int = 180,
        node_lock_ttl: int = 300,
        manifest_id: Optional[str] = None,
        db=None,
        instance_selection_service=None,
    ) -> Dict[str, str]:
        """Returns {node_name: status} where status ∈ READY|FAILED_TIMEOUT|REUSED|SKIPPED_LOCK_HELD|DEFERRED_RATE_LIMIT"""
        r = _get_redis()
        results: Dict[str, str] = {}
        new_count = 0

        iss = instance_selection_service
        # Load existing overrides for this manifest (crash-resume path, Problem 17)
        all_overrides: Dict[str, Dict] = {}
        if manifest_id and db:
            try:
                all_overrides = ExecutionOverrideStore.read_all(manifest_id, db)
            except Exception:
                pass

        for entry in node_plan:
            if entry.get("action") != "provision":
                continue

            node_name = entry.get("node_name", "")
            az        = entry.get("az", "")
            capacity_type = entry.get("capacity_type", "spot")

            # Problem 17 — re-derive working entry from manifest + overrides (never chain)
            working_entry = {**entry, **all_overrides.get(node_name, {})}
            instance_type = working_entry.get("instance_type", "")

            # Per-node lock
            node_lock_key = f"spot:node_lock:{node_name}"
            if r and not r.set(node_lock_key, "provisioning", nx=True, ex=node_lock_ttl):
                logger.warning(f"[NodeProvisioner] Node lock held for {node_name}")
                results[node_name] = "SKIPPED_LOCK_HELD"
                continue

            try:
                # Check for reusable draining node in same AZ + capacity type
                reusable = NodeProvisioner._find_reusable_node(cluster_id, az, capacity_type)
                if reusable:
                    logger.info(f"[NodeProvisioner] Reusing draining node {reusable} for {node_name}")
                    NodeProvisioner._uncordon_node(cluster_id, reusable)
                    results[node_name] = "REUSED"
                    continue

                # Rate limit
                if new_count >= max_nodes_per_cycle:
                    logger.warning(f"[NodeProvisioner] Rate limit ({max_nodes_per_cycle}/cycle) — deferring {node_name}")
                    results[node_name] = "DEFERRED_RATE_LIMIT"
                    continue

                if not instance_type:
                    logger.error(
                        "[NodeProvisioner] provision_entry has no instance_type — "
                        "InstanceSelectionService must resolve before EE runs. "
                        "node=%s manifest=%s", node_name, manifest_id
                    )
                    results[node_name] = "FAILED_NO_INSTANCE_TYPE"
                    continue

                # Trigger provisioning via Karpenter NodePool sync
                NodeProvisioner._trigger_provision(cluster_id, instance_type, az, capacity_type)
                new_count += 1

                # Poll WIE cache for Ready
                ready = NodeProvisioner._wait_for_ready(cluster_id, node_name, node_ready_timeout)
                if ready:
                    results[node_name] = "READY"
                    continue

                # Pool failed — attempt mid-run re-resolution if ISS injected (Problem 11)
                results[node_name] = "FAILED_TIMEOUT"
                if iss is None or db is None or manifest_id is None:
                    continue

                try:
                    pool_key = f"{instance_type}:{az}"
                    iss.selector.de.report_launch_failure(
                        cluster_id=cluster_id,
                        pool_key=pool_key,
                        reason="karpenter_timeout",
                    )
                    policy = iss._load_placement_policy(cluster_id)
                    re_resolved = iss._resolve_with_escalation(
                        cluster_id=cluster_id,
                        entry=working_entry,
                        policy=policy,
                        diversify=False,
                        exec_cache={},
                    )
                    if len(re_resolved) > 1:
                        # Problem 13 — mid-run split: abort, signal replan
                        raise ReplanRequiredError(
                            f"[NodeProvisioner] density split triggered mid-run for "
                            f"cluster={cluster_id} node={node_name}. Aborting group.",
                            original_entry=entry,
                            split_entries=re_resolved,
                        )
                    new_type = re_resolved[0]["instance_type"]
                    # Problem 17 — write override BEFORE retry; re-derive working entry
                    ExecutionOverrideStore.write(
                        manifest_id=manifest_id,
                        node_name=node_name,
                        field="instance_type",
                        original_value=entry.get("instance_type"),
                        override_value=new_type,
                        reason="pool_failure_retry",
                        db=db,
                    )
                    all_overrides = ExecutionOverrideStore.read_all(manifest_id, db)
                    # Retry provisioning with new type
                    NodeProvisioner._trigger_provision(cluster_id, new_type, az, capacity_type)
                    ready2 = NodeProvisioner._wait_for_ready(cluster_id, node_name, node_ready_timeout)
                    results[node_name] = "READY" if ready2 else "FAILED_TIMEOUT"

                except ReplanRequiredError:
                    raise
                except Exception as _iss_err:
                    logger.error("[NodeProvisioner] ISS re-resolution failed: %s", _iss_err)

            finally:
                if r and results.get(node_name) not in ("REUSED",):
                    r.delete(node_lock_key)

        return results

    @staticmethod
    def _find_reusable_node(cluster_id: str, az: str, capacity_type: str) -> Optional[str]:
        for node in _read_wie_draining_nodes(cluster_id):
            if node.get("az") == az and node.get("capacity_type") == capacity_type:
                return node.get("node_name")
        return None

    @staticmethod
    def _trigger_provision(cluster_id: str, instance_type: str, az: str, capacity_type: str) -> None:
        try:
            from backend.services.karpenter_service import KarpenterService
            from backend.core.database import SessionLocal
            db = SessionLocal()
            try:
                svc = KarpenterService(db=db)
                top_pools = [{"instance_type": instance_type, "az": az}]
                svc.sync_ml_rankings_to_nodepool(
                    cluster_id=cluster_id,
                    top_pools=top_pools,
                    capacity_type=capacity_type,
                )
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"[NodeProvisioner] _trigger_provision failed: {exc}")
            raise

    @staticmethod
    def _uncordon_node(cluster_id: str, node_name: str) -> None:
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            from backend.core.database import SessionLocal
            db = SessionLocal()
            try:
                action = AgentAction(
                    cluster_id=cluster_id,
                    action_type=AgentActionType.UNCORDON_NODE,
                    status=AgentActionStatus.PENDING,
                    payload={"node_name": node_name, "source": "node_provisioner:reuse"},
                )
                db.add(action)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"[NodeProvisioner] _uncordon_node failed: {exc}")

    @staticmethod
    def _wait_for_ready(cluster_id: str, node_name: str, timeout: int) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = _read_wie_node_state(cluster_id, node_name)
            if state and state.get("ready") is True:
                return True
            time.sleep(10)
        return False


# ---------------------------------------------------------------------------
# Layer 6 — StatefulExecutor  (BLUE_GREEN groups)
# ---------------------------------------------------------------------------

class StatefulExecutor:
    """
    Drives state machine for BLUE_GREEN groups.
    Sequential within a group — one pod at a time.
    StatefulSet pods executed in reverse ordinal order (pod-N first, pod-0 last).
    """

    @staticmethod
    def execute_group(
        cluster_id: str,
        execution_id: str,
        group: Dict,
        db,
        dry_run: bool = False,
    ) -> str:
        """Returns COMPLETED | ABORTED | PARTIAL"""
        steps = group.get("steps", [])
        # Reverse ordinal order: pod-2 → pod-1 → pod-0
        steps = sorted(steps, key=lambda s: _extract_ordinal(s.get("pod_name", "")), reverse=True)

        completed_count = 0
        for step in steps:
            result = StatefulExecutor._execute_step(cluster_id, execution_id, step, db, dry_run)
            if result == "ABORTED":
                logger.error(
                    f"[StatefulExecutor] group={group.get('group_id')} pod={step.get('pod_name')} ABORTED — stopping group"
                )
                return "ABORTED"
            if result == "COMPLETED":
                completed_count += 1

        if completed_count == 0 and steps:
            return "ABORTED"
        if completed_count < len(steps):
            return "PARTIAL"
        return "COMPLETED"

    @staticmethod
    def execute_wave(
        cluster_id: str,
        execution_id: str,
        groups: List[Dict],
        max_concurrent: int,
        db,
        dry_run: bool = False,
    ) -> Dict[str, str]:
        """Run up to max_concurrent BLUE_GREEN groups in parallel.
        Returns {group_id: COMPLETED|ABORTED|PARTIAL}.
        """
        if not groups:
            return {}
        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(groups))) as executor:
            futures = {
                executor.submit(
                    StatefulExecutor.execute_group,
                    cluster_id, execution_id, group, db, dry_run
                ): group.get("group_id", "unknown")
                for group in groups
            }
            for future in as_completed(futures):
                gid = futures[future]
                try:
                    results[gid] = future.result()
                except Exception as exc:
                    logger.error(f"[StatefulExecutor] wave group={gid} exception: {exc}")
                    results[gid] = "ABORTED"
        return results

    @staticmethod
    def _execute_step(
        cluster_id: str,
        execution_id: str,
        step: Dict,
        db,
        dry_run: bool,
    ) -> str:
        pod_name = step.get("pod_name", "")
        namespace = step.get("namespace", "default")
        target_node = step.get("to_node") or step.get("target_node", "")
        from_node = step.get("from_node", "")
        rollback_map = step.get("rollback", {})
        stability_window = step.get("stability_window_seconds", 60)
        traffic_mechanism = step.get("traffic_shift_mechanism", "service_selector_patch")

        # ── PRE-FLIGHT: PVC AZ check ───────────────────────────────────────
        if step.get("has_pvc"):
            pvc_az = _lookup_pvc_az(db, pod_name)
            target_az = step.get("to_az") or step.get("target_az")
            if pvc_az and target_az and pvc_az != target_az:
                logger.warning(f"[StatefulExecutor] PVC AZ mismatch pod={pod_name} pvc={pvc_az} target={target_az}")
                return "DEFERRED"

        # ── PRE-FLIGHT: max_pods check ─────────────────────────────────────
        pod_count = _read_wie_node_pod_count(cluster_id, target_node)
        if pod_count is not None and pod_count >= 110:
            logger.warning(f"[StatefulExecutor] max_pods on {target_node} ({pod_count}) — pod={pod_name} DEFERRED")
            return "DEFERRED"

        # Write-ahead log before touching anything
        ActionTracker.start(cluster_id, execution_id, pod_name, "BLUE_GREEN", from_node, target_node)

        try:
            if not dry_run:
                # PROVISIONING_NEW — patch affinity to target node
                affinity_id = _patch_affinity(cluster_id, pod_name, namespace, target_node, db)
                ActionTracker.add_agent_action(cluster_id, execution_id, pod_name, affinity_id)

                # WAITING_READY — wait for new pod on target
                if not _wait_pod_running(cluster_id, pod_name, target_node, timeout=180):
                    _execute_rollback(cluster_id, rollback_map, pod_name, namespace, db)
                    ActionTracker.fail(cluster_id, execution_id, pod_name, "new_pod_not_ready_timeout")
                    return "ABORTED"

                # SHIFTING_TRAFFIC
                if not _shift_traffic(cluster_id, pod_name, namespace, traffic_mechanism, step, db):
                    _execute_rollback(cluster_id, rollback_map, pod_name, namespace, db)
                    ActionTracker.fail(cluster_id, execution_id, pod_name, "traffic_shift_failed")
                    return "ABORTED"

                # OBSERVING — stability window
                time.sleep(min(stability_window, 120))  # cap at 2 min to avoid task starvation
                if not _pod_still_healthy(cluster_id, pod_name, target_node):
                    _execute_rollback(cluster_id, rollback_map, pod_name, namespace, db)
                    ActionTracker.fail(cluster_id, execution_id, pod_name, "stability_check_failed")
                    return "ABORTED"

                # DELETING_OLD — evict the old pod only after OBSERVING passes
                evict_id = _evict_pod_action(cluster_id, pod_name, namespace, from_node, db)
                ActionTracker.add_agent_action(cluster_id, execution_id, pod_name, evict_id)

            ActionTracker.complete(cluster_id, execution_id, pod_name)
            return "COMPLETED"

        except Exception as exc:
            ActionTracker.fail(cluster_id, execution_id, pod_name, str(exc))
            _execute_rollback(cluster_id, rollback_map, pod_name, namespace, db)
            return "ABORTED"


# ---------------------------------------------------------------------------
# Layer 7 — StatelessExecutor  (BATCH groups)
# ---------------------------------------------------------------------------

class StatelessExecutor:
    """
    BATCH groups run in parallel with each other.
    Within each group, batches run sequentially.
    Individual pod failures → log + continue. All-pod failure → stop group.
    """

    @staticmethod
    def execute_all(
        cluster_id: str,
        execution_id: str,
        groups: List[Dict],
        db,
        dry_run: bool = False,
        max_concurrent: int = 5,
    ) -> Dict[str, str]:
        """Returns {group_id: COMPLETED|PARTIAL|FAILED}"""
        if not groups:
            return {}

        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(groups))) as executor:
            futures = {
                executor.submit(
                    StatelessExecutor._execute_group,
                    cluster_id, execution_id, group, db, dry_run
                ): group.get("group_id", "unknown")
                for group in groups
            }
            for future in as_completed(futures):
                gid = futures[future]
                try:
                    results[gid] = future.result()
                except Exception as exc:
                    logger.error(f"[StatelessExecutor] group={gid} unhandled exception: {exc}")
                    results[gid] = "FAILED"

        return results

    @staticmethod
    def _execute_group(
        cluster_id: str,
        execution_id: str,
        group: Dict,
        db,
        dry_run: bool,
    ) -> str:
        batches = group.get("batches", [])
        any_completed = False

        for batch in batches:
            result = StatelessExecutor._execute_batch(cluster_id, execution_id, batch, db, dry_run)
            if result == "ALL_FAILED":
                return "PARTIAL" if any_completed else "FAILED"
            if result in ("COMPLETED", "PARTIAL"):
                any_completed = True

        return "COMPLETED" if any_completed or not batches else "FAILED"

    @staticmethod
    def _execute_step_for_node(
        cluster_id: str,
        execution_id: str,
        node_steps: List[Dict],
        db,
        dry_run: bool,
    ) -> int:
        """Execute steps for a single target node sequentially. Returns failed count."""
        failed = 0
        for step in node_steps:
            pod_name = step.get("pod_name", "")
            namespace = step.get("namespace", "default")
            target_node = step.get("to_node") or step.get("target_node", "")
            from_node = step.get("from_node", "")

            pod_count = _read_wie_node_pod_count(cluster_id, target_node)
            if pod_count is not None and pod_count >= 110:
                logger.warning(f"[StatelessExecutor] max_pods on {target_node} — skipping {pod_name}")
                failed += 1
                continue

            ActionTracker.start(cluster_id, execution_id, pod_name, "BATCH", from_node, target_node)
            try:
                if not dry_run:
                    affinity_id = _patch_affinity(cluster_id, pod_name, namespace, target_node, db)
                    ActionTracker.add_agent_action(cluster_id, execution_id, pod_name, affinity_id)

                    evict_id = _evict_pod_action(cluster_id, pod_name, namespace, from_node, db)
                    ActionTracker.add_agent_action(cluster_id, execution_id, pod_name, evict_id)

                    if not _wait_pod_running(cluster_id, pod_name, target_node, timeout=60):
                        ActionTracker.fail(cluster_id, execution_id, pod_name, "pod_not_ready_timeout")
                        failed += 1
                        continue

                ActionTracker.complete(cluster_id, execution_id, pod_name)

            except Exception as exc:
                ActionTracker.fail(cluster_id, execution_id, pod_name, str(exc))
                failed += 1
        return failed

    @staticmethod
    def _execute_batch(
        cluster_id: str,
        execution_id: str,
        batch: Dict,
        db,
        dry_run: bool,
    ) -> str:
        steps = batch.get("steps", [])
        if not steps:
            return "COMPLETED"

        # Group steps by target node — pods to different nodes can run in parallel;
        # pods targeting the same node must be sequential to avoid capacity race.
        by_node: Dict[str, List[Dict]] = defaultdict(list)
        for step in steps:
            node_key = step.get("to_node") or step.get("target_node") or "_unknown"
            by_node[node_key].append(step)

        failed = 0
        with ThreadPoolExecutor(max_workers=min(4, len(by_node))) as ex:
            futures = {
                ex.submit(
                    StatelessExecutor._execute_step_for_node,
                    cluster_id, execution_id, node_steps, db, dry_run
                ): node
                for node, node_steps in by_node.items()
            }
            for future in as_completed(futures):
                try:
                    failed += future.result()
                except Exception as exc:
                    logger.error(f"[StatelessExecutor] node batch exception: {exc}")
                    failed += 1

        if failed == len(steps):
            return "ALL_FAILED"
        if failed > 0:
            return "PARTIAL"
        return "COMPLETED"


# ---------------------------------------------------------------------------
# Layer 8 — Verifier
# ---------------------------------------------------------------------------

class Verifier:
    """
    Post-execution check. Reads WIE cache, compares against manifest expectations.
    DEFERRED and BLOCKED steps are intentional — not counted as mismatches.
    """

    @staticmethod
    def verify(cluster_id: str, manifest: Dict) -> Dict:
        """
        Returns {
            matched: [pod_name, ...],
            mismatched: [{pod_name, expected_node, actual_node, reason}, ...],
            skipped: [pod_name, ...],
        }
        """
        matched: List[str] = []
        mismatched: List[Dict] = []
        skipped: List[str] = []

        for step in _collect_all_steps(manifest):
            pod_name = step.get("pod_name", "")
            status = step.get("status", "")

            # Skip intentionally deferred/blocked/failed steps
            if status in ("DEFERRED", "BLOCKED", "FAILED"):
                skipped.append(pod_name)
                continue

            expected_node = step.get("to_node") or step.get("target_node", "")
            wie_pod = _read_wie_pod_state(cluster_id, pod_name)

            if wie_pod is None:
                mismatched.append({"pod_name": pod_name, "reason": "pod_not_found"})
                continue

            actual_node = wie_pod.get("node_name", "")
            phase = wie_pod.get("phase", "")

            if actual_node != expected_node:
                mismatched.append({
                    "pod_name": pod_name,
                    "expected_node": expected_node,
                    "actual_node": actual_node,
                    "reason": "wrong_node",
                })
            elif phase not in ("Running", "Succeeded"):
                mismatched.append({
                    "pod_name": pod_name,
                    "reason": f"not_running:{phase}",
                    "actual_node": actual_node,
                })
            else:
                matched.append(pod_name)

        return {"matched": matched, "mismatched": mismatched, "skipped": skipped}


# ---------------------------------------------------------------------------
# Layer 9 — FeedbackHandler
# ---------------------------------------------------------------------------

class FeedbackHandler:
    """
    Classifies Verifier mismatches. Sets scoped Redis replan signals.
    Never triggers a full system replan — only cluster-scoped signals.
    """

    MISMATCH_RATE_THRESHOLD = 0.5  # >50% mismatches → increment circuit breaker

    @staticmethod
    def handle(
        cluster_id: str,
        verification_result: Dict,
        circuit_breaker_window: int = 600,
    ) -> None:
        mismatches = verification_result.get("mismatched", [])
        matched = verification_result.get("matched", [])

        wrong_node_count = 0
        not_running_count = 0

        for m in mismatches:
            reason = m.get("reason", "")
            if reason == "wrong_node":
                wrong_node_count += 1
            elif reason.startswith("not_running"):
                not_running_count += 1
            elif reason == "pod_not_found":
                logger.warning(
                    f"[FeedbackHandler] cluster={cluster_id} pod={m.get('pod_name')} not found post-migration"
                )

        if wrong_node_count > 0 or not_running_count > 0:
            _signal_replan(
                cluster_id,
                f"post_execution_mismatch:wrong_node={wrong_node_count},not_running={not_running_count}",
            )

        total_steps = len(matched) + len(mismatches)
        if total_steps > 0 and len(mismatches) / total_steps > FeedbackHandler.MISMATCH_RATE_THRESHOLD:
            _increment_circuit_breaker(cluster_id, window_seconds=circuit_breaker_window)
            logger.warning(
                f"[FeedbackHandler] cluster={cluster_id} mismatch_rate={len(mismatches)/total_steps:.0%} — circuit breaker incremented"
            )


# ---------------------------------------------------------------------------
# Layer 10 — ExecutionEngine  (Orchestrator)
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """
    Owns cluster state transitions. Wires all 9 layers.
    The finally block is non-negotiable — IDLE must always be restored.
    """

    # Cluster state values written to Redis (Medium B: explicit sub-states for UI)
    STATE_IDLE                = "IDLE"
    STATE_PROVISIONING        = "PROVISIONING"        # node launch in progress
    STATE_EXECUTING           = "EXECUTING"            # stateful (BLUE_GREEN) phase
    STATE_EXECUTING_STATELESS = "EXECUTING_STATELESS"  # batch phase
    STATE_DRAINING            = "DRAINING"             # drain + terminate in progress
    STATE_VERIFYING           = "VERIFYING"            # post-execution verification
    STATE_FAILED              = "FAILED"               # terminal: unhandled error
    STATE_PARTIAL             = "PARTIAL"              # completed with mismatches > threshold

    # Medium B: human-readable status map consumed by /api/clusters/{id}/execution/status
    STATE_LABELS: Dict[str, str] = {
        "IDLE":                "Idle",
        "PROVISIONING":        "Provisioning nodes",
        "EXECUTING":           "Migrating stateful workloads",
        "EXECUTING_STATELESS": "Migrating batch workloads",
        "DRAINING":            "Draining vacated nodes",
        "VERIFYING":           "Verifying placement",
        "FAILED":              "Execution failed",
        "PARTIAL":             "Completed with warnings",
    }

    @staticmethod
    def _set_state(r, cluster_id: str, state: str) -> None:
        """Write state to Redis + update manifest last_heartbeat indirectly via state key."""
        if r:
            r.set(f"spot:cluster:state:{cluster_id}", state)

    @staticmethod
    def get_state_label(state: str) -> str:
        return ExecutionEngine.STATE_LABELS.get(state, state)

    @staticmethod
    def _manifest_still_valid(manifest_id: str, db) -> bool:
        """
        Problem 22 — uses blocking with_for_update() (NOT skip_locked).
        Problem 29 — READ COMMITTED isolation so the lock reads committed state.
        Returns False if manifest was transitioned to EXPIRED/FAILED/COMPLETED by TTLMonitor.
        """
        try:
            from sqlalchemy import text
            from backend.models.execution_manifest import ExecutionManifest
            db.execute(text(
                "SET LOCAL TRANSACTION ISOLATION LEVEL READ COMMITTED"
            ))
            row = db.query(ExecutionManifest).filter(
                ExecutionManifest.manifest_id == manifest_id
            ).with_for_update().first()  # blocking — NOT skip_locked (Problem 22)
            if not row:
                return False
            return row.status not in ("EXPIRED", "FAILED", "COMPLETED")
        except Exception as e:
            logger.debug("[EE] _manifest_still_valid check failed (assume valid): %s", e)
            return True

    @staticmethod
    def run(
        cluster_id: str,
        manifest: Dict,
        db,
        dry_run: bool = False,
        instance_selection_service=None,  # Problem 11: optional ISS for mid-run retry
    ) -> None:
        r = _get_redis()
        lock_key = f"spot:ee:exec_lock:{cluster_id}"
        execution_id = manifest.get("manifest_id") or str(uuid.uuid4())

        # Load settings live from DB
        circuit_threshold = 10
        cooldown_seconds = 0
        node_lock_ttl = 300
        node_ready_timeout = 180
        max_nodes_per_cycle = 3
        circuit_window = 600
        try:
            from backend.models.cluster import Cluster
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster:
                settings = getattr(cluster, "optimization_settings", None)
                if settings:
                    circuit_threshold = getattr(settings, "execution_circuit_breaker_threshold", 10) or 10
                    cooldown_seconds = getattr(settings, "post_execution_cooldown_seconds", 0) or 0
                    node_lock_ttl = getattr(settings, "node_lock_ttl_seconds", 300) or 300
                    node_ready_timeout = getattr(settings, "node_ready_timeout_seconds", 180) or 180
                    max_nodes_per_cycle = getattr(settings, "max_nodes_provisioned_per_cycle", 3) or 3
                    circuit_window = getattr(settings, "execution_circuit_breaker_window_seconds", 600) or 600
        except Exception as exc:
            logger.debug(f"[EE] settings load failed (using defaults): {exc}")

        # ── ONBOARDING PHASE GATE (manifest_type-aware) ─────────────────────
        # shadow   → block ALL manifests
        # takeover → block optimization manifests only; allow manifest_type=takeover
        # managed  → allow all (fall through)
        try:
            _ob_phase = getattr(cluster, 'onboarding_phase', 'managed') or 'managed'
            if _ob_phase in ('shadow', 'takeover'):
                _manifest_type = manifest.get('manifest_type', 'optimization')
                if _ob_phase == 'shadow' or _manifest_type != 'takeover':
                    logger.info(
                        f"[EE] cluster={cluster_id} onboarding_gate phase={_ob_phase} "
                        f"manifest_type={_manifest_type} — skipping"
                    )
                    return
        except Exception:
            pass  # fail open

        # ── GATE CHECK ──────────────────────────────────────────────────────
        passed, reason = ExecutionGate.check(
            cluster_id, manifest,
            circuit_breaker_threshold=circuit_threshold,
            post_execution_cooldown_seconds=cooldown_seconds,
        )
        if not passed:
            logger.info(f"[EE] cluster={cluster_id} gate_failed reason={reason}")
            return

        try:
            # ── STATE: EXECUTING ────────────────────────────────────────────
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_EXECUTING)

            # ── RACE CHECK ──────────────────────────────────────────────────
            race_ok, race_reason = RaceGuard.check(cluster_id, manifest)
            if not race_ok:
                logger.info(f"[EE] cluster={cluster_id} race_guard_abort reason={race_reason}")
                return

            # ── DB: EXECUTING ────────────────────────────────────────────────
            ManifestStore.transition(execution_id, "EXECUTING", db, r)

            # ── STATE: PROVISIONING (Medium B) ───────────────────────────
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_PROVISIONING)

            # ── NODE PROVISIONING ───────────────────────────────────────────
            node_plan = manifest.get("node_plan", [])
            if node_plan:
                provision_entries = [e for e in node_plan if e.get("action") == "provision"]
                if provision_entries:
                    try:
                        node_results = NodeProvisioner.provision_all(
                            cluster_id=cluster_id,
                            node_plan=provision_entries,
                            max_nodes_per_cycle=max_nodes_per_cycle,
                            node_ready_timeout=node_ready_timeout,
                            node_lock_ttl=node_lock_ttl,
                            manifest_id=execution_id,
                            db=db,
                            instance_selection_service=instance_selection_service,
                        )
                    except ReplanRequiredError as _rpe:
                        logger.error(
                            "[EE] cluster=%s ReplanRequired during provisioning: %s",
                            cluster_id, _rpe
                        )
                        ManifestStore.transition(execution_id, "FAILED", db, r)
                        _signal_replan(cluster_id, f"provision_split:{execution_id}")
                        _increment_circuit_breaker(cluster_id, circuit_window)
                        return
                    for node_name, result in node_results.items():
                        if result in ("FAILED_TIMEOUT", "FAILED_NO_INSTANCE_TYPE"):
                            logger.error(f"[EE] Node {node_name} failed ({result}) — aborting")
                            _increment_circuit_breaker(cluster_id, circuit_window)
                            return
            ManifestStore.heartbeat(execution_id, db)

            # ── STATEFUL EXECUTION — wave-based ─────────────────────────────
            parallel_waves = manifest.get("parallel_waves") or []
            stateful_waves = [
                w for w in parallel_waves
                if w.get("workload_class") in ("stateful", "db")
            ]
            gid_to_group = {
                g.get("group_id"): g
                for g in manifest.get("migration_groups", [])
                if (g.get("workload_class") or "").lower() != "system"
            }

            if stateful_waves:
                # Wave-based path: respects dependency ordering and concurrency caps
                for wave in stateful_waves:
                    if not ExecutionEngine._manifest_still_valid(execution_id, db):
                        logger.warning(
                            "[EE] cluster=%s manifest=%s expired by TTLMonitor — aborting at BG wave",
                            cluster_id, execution_id
                        )
                        return
                    wave_idx = wave.get("wave_index", 0)
                    wave_groups = [
                        gid_to_group[gid]
                        for gid in (wave.get("group_ids") or [])
                        if gid in gid_to_group
                    ]
                    max_conc = wave.get("max_concurrent", 1)
                    # Part 8: Redis wave tracking
                    if r:
                        r.set(
                            f"spot:ee:wave:{cluster_id}",
                            f"stateful:wave{wave_idx}:{len(wave_groups)}groups",
                        )
                    logger.info(
                        "[EE] cluster=%s stateful wave=%d groups=%d max_concurrent=%d",
                        cluster_id, wave_idx, len(wave_groups), max_conc
                    )
                    results = StatefulExecutor.execute_wave(
                        cluster_id, execution_id, wave_groups, max_conc, db, dry_run
                    )
                    aborted = [gid for gid, r_ in results.items() if r_ == "ABORTED"]
                    if aborted:
                        logger.error("[EE] cluster=%s wave=%d groups ABORTED: %s — stopping", cluster_id, wave_idx, aborted)
                        _increment_circuit_breaker(cluster_id, circuit_window)
                        return
                    ManifestStore.heartbeat(execution_id, db)
            else:
                # Fallback: no wave metadata — sequential per group (backward compat)
                blue_green_groups = [
                    g for g in manifest.get("migration_groups", [])
                    if g.get("type") in ("BLUE_GREEN", "SERIAL")
                    and (g.get("workload_class") or "").lower() != "system"
                ]
                for group in blue_green_groups:
                    if not ExecutionEngine._manifest_still_valid(execution_id, db):
                        logger.warning(
                            "[EE] cluster=%s manifest=%s expired by TTLMonitor — aborting at BG phase",
                            cluster_id, execution_id
                        )
                        return
                    result = StatefulExecutor.execute_group(cluster_id, execution_id, group, db, dry_run)
                    if result == "ABORTED":
                        logger.error(f"[EE] BLUE_GREEN group={group.get('group_id')} ABORTED — stopping")
                        _increment_circuit_breaker(cluster_id, circuit_window)
                        return
                    ManifestStore.heartbeat(execution_id, db)

            # ── STATE: EXECUTING_STATELESS ──────────────────────────────
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_EXECUTING_STATELESS)

            # ── STATELESS EXECUTION — wave-based ─────────────────────────────
            stateless_waves = [
                w for w in parallel_waves
                if w.get("workload_class") in ("stateless", "mixed", "batch")
            ]

            if not ExecutionEngine._manifest_still_valid(execution_id, db):
                logger.warning(
                    "[EE] cluster=%s manifest=%s expired before stateless phase",
                    cluster_id, execution_id
                )
                return

            if stateless_waves:
                for wave in stateless_waves:
                    wave_idx = wave.get("wave_index", 0)
                    wave_groups = [
                        gid_to_group[gid]
                        for gid in (wave.get("group_ids") or [])
                        if gid in gid_to_group
                    ]
                    max_conc = wave.get("max_concurrent", 5)
                    if r:
                        r.set(
                            f"spot:ee:wave:{cluster_id}",
                            f"stateless:wave{wave_idx}:{len(wave_groups)}groups",
                        )
                    logger.info(
                        "[EE] cluster=%s stateless wave=%d groups=%d max_concurrent=%d",
                        cluster_id, wave_idx, len(wave_groups), max_conc
                    )
                    StatelessExecutor.execute_all(
                        cluster_id, execution_id, wave_groups, db, dry_run,
                        max_concurrent=max_conc,
                    )
                    ManifestStore.heartbeat(execution_id, db)
            else:
                # Fallback: no wave metadata — all batch groups in one shot
                batch_groups = [
                    g for g in manifest.get("migration_groups", [])
                    if g.get("type") in ("BATCH", "ROLLING")
                    and (g.get("workload_class") or "").lower() != "system"
                ]
                if batch_groups:
                    StatelessExecutor.execute_all(cluster_id, execution_id, batch_groups, db, dry_run)
                ManifestStore.heartbeat(execution_id, db)

            # Clean up wave tracking key
            if r:
                r.delete(f"spot:ee:wave:{cluster_id}")

            # ── STATE: DRAINING ───────────────────────────────────────────
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_DRAINING)

            drain_entries = [e for e in node_plan if e.get("action") == "drain"]
            for entry in drain_entries:
                ExecutionEngine._drain_node(cluster_id, entry, db, node_lock_ttl)

            # ── STATE: VERIFYING ───────────────────────────────────────────
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_VERIFYING)

            verification = Verifier.verify(cluster_id, manifest)
            FeedbackHandler.handle(cluster_id, verification, circuit_window)

            # Medium B — PARTIAL state when mismatches exceed threshold
            _v_matched   = len(verification.get("matched", []))
            _v_mismatched = len(verification.get("mismatched", []))
            _v_total = _v_matched + _v_mismatched
            if _v_total > 0 and (_v_mismatched / _v_total) > FeedbackHandler.MISMATCH_RATE_THRESHOLD:
                ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_PARTIAL)

            # ── COST RECOMPUTE from actual state ─────────────────────────────
            ExecutionEngine._recompute_cost_from_actual(cluster_id)

            # ── POST-EXECUTION COOLDOWN (opt-in) ─────────────────────────────
            if cooldown_seconds > 0 and r:
                r.setex(f"spot:ee:cooldown:{cluster_id}", cooldown_seconds, "1")

            # DB: COMPLETED
            ManifestStore.transition(execution_id, "COMPLETED", db, r)
            # Clean up manifest Redis cache — DB row kept for audit
            ManifestStore.delete(cluster_id)

            logger.info(
                f"[EE] cluster={cluster_id} execution_id={execution_id} completed "
                f"matched={len(verification.get('matched', []))} "
                f"mismatched={len(verification.get('mismatched', []))} "
                f"skipped={len(verification.get('skipped', []))}"
            )

        except Exception as exc:
            logger.error(f"[EE] cluster={cluster_id} unhandled exception: {exc}", exc_info=True)
            ExecutionEngine._set_state(r, cluster_id, ExecutionEngine.STATE_FAILED)
            _increment_circuit_breaker(cluster_id, circuit_window)
            raise

        finally:
            # ALWAYS release lock and reset state — no exceptions tolerated
            if r:
                r.delete(lock_key)
                r.set(f"spot:cluster:state:{cluster_id}", ExecutionEngine.STATE_IDLE)

    @staticmethod
    def _drain_node(cluster_id: str, entry: Dict, db, node_lock_ttl: int = 300) -> None:
        node_name = entry.get("node_name", "")
        r = _get_redis()

        # Per-node lock
        node_lock_key = f"spot:node_lock:{node_name}"
        if r and not r.set(node_lock_key, "draining", nx=True, ex=node_lock_ttl):
            logger.warning(f"[EE] Node lock held for {node_name} — skipping drain")
            return

        try:
            # PDB re-check before every drain
            if not _pdb_safe_to_drain(node_name, db):
                logger.warning(f"[EE] PDB unsafe for {node_name} — skipping drain (deferred)")
                entry["status"] = "DEFERRED"
                return

            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            drain_action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.DRAIN_NODE,
                status=AgentActionStatus.PENDING,
                priority=10,
                payload={"node_name": node_name, "ignore_daemonsets": True, "source": "execution_engine"},
            )
            db.add(drain_action)

            terminate_action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.TERMINATE_NODE,
                status=AgentActionStatus.PENDING,
                priority=10,
                payload={"node_name": node_name, "source": "execution_engine"},
            )
            db.add(terminate_action)
            db.commit()

            logger.info(f"[EE] Dispatched DRAIN_NODE + TERMINATE_NODE for {node_name}")

        except Exception as exc:
            logger.error(f"[EE] _drain_node failed for {node_name}: {exc}")
        finally:
            if r:
                r.delete(node_lock_key)

    @staticmethod
    def _recompute_cost_from_actual(cluster_id: str) -> None:
        try:
            actual_nodes = _read_wie_all_nodes(cluster_id)
            total_cost = sum(
                _lookup_instance_price(
                    n.get("instance_type", ""),
                    n.get("capacity_type", "on-demand"),
                )
                for n in actual_nodes
            )
            r = _get_redis()
            if r:
                r.setex(f"spot:cluster:actual_cost_hr:{cluster_id}", 600, str(round(total_cost, 4)))
            logger.info(f"[EE] Actual post-execution cost: ${total_cost:.4f}/hr for cluster {cluster_id}")
        except Exception as exc:
            logger.debug(f"[EE] _recompute_cost_from_actual failed: {exc}")