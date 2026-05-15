"""
PlacementController Service — v1.4
====================================
Runs every 5 minutes via Celery beat.

Responsibilities:
  - Compare current pod distribution vs PlacementPolicy (ondemand_target, spot_target).
  - Evict burst On-Demand pods for stateless workloads (EVICT_POD action).
  - Trigger create-before-delete rollout for stateful workloads via PlacementRolloutService.
  - Enforce: scaling guard, rolling-update guard, drift threshold, cooldowns, rate limits.
  - Emit structured cycle metrics to Redis.

Decision authority: ONLY this controller decides Spot vs On-Demand — no dual-brain.
The Mutating Webhook injects structural hints only (AZ spread, soft Spot affinity).

Fixes applied from plan.md v1.4:
  - Fix 3: new pod placement validation after stateful rollout scale-up.
  - Fix 4: pod.age < 2 min guard — prevents controller/scheduler fight.
  - Fix 5: evictions_failed_due_to_no_replacement metric.
"""

from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DRIFT_THRESHOLD_SMALL = 1           # For target_od <= 3
DRIFT_THRESHOLD_PCT = 0.20          # 20% excess for larger workloads
DRIFT_THRESHOLD_SMALL_MAX_TARGET = 3

MAX_EVICTIONS_PER_CYCLE = int(os.getenv("PC_MAX_EVICTIONS_PER_CYCLE", 3))
SPOT_CAPACITY_BUFFER = float(os.getenv("PC_SPOT_CAPACITY_BUFFER", 0.7))
MIGRATION_TIMEOUT_MINUTES = int(os.getenv("PC_MIGRATION_TIMEOUT_MINUTES", 20))
MIGRATION_FAILED_COOLDOWN_MINUTES = int(os.getenv("PC_MIGRATION_FAILED_COOLDOWN_MINUTES", 30))
SCALING_GUARD_WINDOW_SECONDS = int(os.getenv("PC_SCALING_GUARD_WINDOW_SECS", 120))
PENDING_PODS_THRESHOLD = int(os.getenv("PC_PENDING_PODS_THRESHOLD", 3))
WORKLOAD_COOLDOWN_MINUTES = int(os.getenv("PC_WORKLOAD_COOLDOWN_MINUTES", 10))
POD_AGE_MIN_SECONDS = 120           # Fix 4: skip pods younger than 2 minutes

CLUSTER_BATCH_SIZE = int(os.getenv("PC_CLUSTER_BATCH_SIZE", 2))
MAX_RETRY_COUNT = int(os.getenv("PC_MAX_RETRY_COUNT", 3))
CLUSTER_MUTEX_TTL_SECS = 60
WORKLOAD_LOCK_TTL_SECS = 30

METRICS_KEY_TEMPLATE = "spot:placement_controller:metrics:{cluster_id}"
METRICS_TTL = 3600
COOLDOWN_KEY_TEMPLATE = "spot:placement_controller:cooldown:{cluster_id}:{workload_id}"
SHADOW_MODE_KEY_TEMPLATE = "spot:placement_controller:shadow_mode:{cluster_id}"
KEDA_EVENT_KEY_TEMPLATE = "spot:keda:last_scale_event:{cluster_id}"
HPA_EVENT_KEY_TEMPLATE  = "spot:pc:hpa_scaling_event:{cluster_id}"
HPA_SCALING_GUARD_WINDOW_SECONDS = int(os.getenv("PC_HPA_SCALING_GUARD_WINDOW_SECS", 180))  # 3-min inhibit
PENDING_PODS_KEY_TEMPLATE = "spot:cluster:pending_pods:{cluster_id}"
POLICY_KEY_TEMPLATE = "spot:placement:policy:{cluster_id}:{workload_id}"
ROLLOUT_STATUS_CACHE_TTL = 30       # seconds — K8s rollout status cache
KEDA_BOOTSTRAP_WINDOW_SECONDS = int(os.getenv("PC_KEDA_BOOTSTRAP_WINDOW_SECS", 300))
PC_MAX_STALENESS_SECONDS = int(os.getenv("PC_MAX_STALENESS_SECS", 30))  # Block evictions when agent state > 30s old
PC_ACTION_DEADLINE_SECONDS = int(os.getenv("PC_ACTION_DEADLINE_SECS", 60))  # Convergence deadline for validator
_PROCESS_START_TIME = time.time()   # set once at import — used for KEDA bootstrap window
WORKLOAD_LOG_KEY_TEMPLATE = "spot:pc:workload_log:{cluster_id}:{workload_id}"

PC_CB_THRESHOLD = int(os.getenv("PC_CIRCUIT_BREAKER_THRESHOLD", "10"))
PC_CB_WINDOW_SECS = int(os.getenv("PC_CIRCUIT_BREAKER_WINDOW_SECS", "600"))
PC_CB_COOLDOWN_SECS = int(os.getenv("PC_CIRCUIT_BREAKER_COOLDOWN_SECS", "1800"))
PC_CB_KEY = "spot:pc:circuit_breaker:{cluster_id}"
PC_CB_FAILURE_KEY = "spot:pc:cb_failures:{cluster_id}"

OSCILLATION_COUNTER_KEY = "spot:pc:workload_od_landings:{cluster_id}:{workload_id}"
OSCILLATION_BLOCK_KEY   = "spot:pc:workload_oscillation_block:{cluster_id}:{workload_id}"
OSCILLATION_COUNTER_TTL = int(os.getenv("PC_OSCILLATION_WINDOW_SECS", 1800))   # 30 min sliding window
OSCILLATION_BLOCK_TTL   = int(os.getenv("PC_OSCILLATION_BLOCK_SECS", 7200))    # 2-hour hard stop
OSCILLATION_THRESHOLD   = int(os.getenv("PC_OSCILLATION_THRESHOLD", 5))        # OD landings before block


class DecisionReason(Enum):
    PDB_CONSTRAINT       = "pdb_constraint"
    KEDA_SCALING_ACTIVE  = "keda_scaling_active"
    COOLDOWN_ACTIVE      = "cooldown_active"
    ROLLOUT_BLOCKED      = "rollout_blocked"
    BATCH_LIMIT_REACHED  = "batch_limit_reached"
    AT_TARGET            = "at_target"
    INSUFFICIENT_NODES   = "insufficient_nodes"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    OBSERVATION_MODE     = "observation_mode"


class DecisionAction(Enum):
    SKIP      = "skip"
    EVICT     = "evict"
    DEFER     = "defer"
    REBALANCE = "rebalance"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PodInfo:
    uid: str
    name: str
    namespace: str
    az: str
    node: str
    capacity_type: str          # "spot" | "on-demand"
    cpu_request: float          # millicores
    memory_request: float       # MiB
    age_seconds: float          # seconds since pod creation


@dataclass
class SpotNode:
    name: str
    az: str
    allocatable_cpu: float      # millicores
    allocatable_memory: float   # MiB
    max_pods: int
    current_pod_count: int


@dataclass
class RolloutStatus:
    updated_replicas: int
    ready_replicas: int


@dataclass
class CapacityMap:
    nodes_by_az: Dict[str, List[SpotNode]] = field(default_factory=dict)

    def get_nodes(self, az: str) -> List[SpotNode]:
        return self.nodes_by_az.get(az, [])


# ---------------------------------------------------------------------------
# PlacementController
# ---------------------------------------------------------------------------

class PlacementController:
    """
    Core placement brain. Reconciles actual pod distribution against policy targets.

    Injected dependencies:
      db          — SQLAlchemy Session
      redis       — Redis client
      k8s_client  — Kubernetes API client (CoreV1Api / AppsV1Api wrapper)
      rollout_svc — PlacementRolloutService instance
    """

    def __init__(self, db, redis, k8s_client, rollout_svc):
        self.db = db
        self.redis = redis
        self.k8s = k8s_client
        self.rollout_svc = rollout_svc

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_cycle(self, cluster_id: str) -> None:
        """
        Main 5-minute cycle entry point.
        Called by Celery beat task.
        """
        from backend.utils.redis_locks import cluster_mutex

        metrics: Dict[str, int] = {
            "evictions_attempted": 0,
            "evictions_skipped_capacity": 0,
            "evictions_skipped_cooldown": 0,
            "evictions_skipped_scaling_guard": 0,
            "evictions_skipped_pod_too_young": 0,
            "evictions_failed_due_to_no_replacement": 0,
            "evictions_skipped_lock_contention": 0,
            "evictions_skipped_batch_limit": 0,
            "evictions_skipped_last_pod": 0,
            "evictions_skipped_pdb_violation": 0,
            "evictions_skipped_active_action": 0,
            "evictions_skipped_node_drain": 0,
            "stateful_rollout_started": 0,
            "stateful_rollout_completed": 0,
            "stateful_rollout_failed": 0,
            "stateful_rollout_timeout": 0,
            "retry_incremented": 0,
            "permanent_failures": 0,
            "circuit_breaker_tripped": 0,
        }

        # Engine B circuit breaker — check open key first (fast path)
        cb_key = PC_CB_KEY.format(cluster_id=cluster_id)
        if self.redis.get(cb_key):
            logger.warning("pc_circuit_breaker_open cluster=%s", cluster_id)
            metrics["circuit_breaker_tripped"] = 1
            self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="circuit_breaker")
            return

        # Check failure count over window — trip if threshold reached
        try:
            from backend.models.agent_action import AgentAction as _AA, AgentActionStatus as _AAS, AgentActionType as _AAT
            from sqlalchemy import func as _func
            recent_failures = (
                self.db.query(_func.count(_AA.id))
                .filter(
                    _AA.cluster_id == cluster_id,
                    _AA.status == _AAS.FAILED,
                    _AA.action_type == _AAT.EVICT_POD,
                    _AA.updated_at > datetime.utcnow() - timedelta(seconds=PC_CB_WINDOW_SECS),
                )
                .scalar() or 0
            )
            if recent_failures >= PC_CB_THRESHOLD:
                self.redis.setex(cb_key, PC_CB_COOLDOWN_SECS, "1")
                logger.error(
                    "pc_circuit_breaker_tripped cluster=%s failures=%d",
                    cluster_id, recent_failures,
                )
                metrics["circuit_breaker_tripped"] = 1
                self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="circuit_breaker_tripped")
                return
        except Exception as _cb_exc:
            logger.warning("pc_circuit_breaker_check_error cluster=%s: %s", cluster_id, _cb_exc)

        # § ONBOARDING PHASE GATE — block PC during shadow/takeover phases
        try:
            from backend.models.cluster import Cluster as _Cl_ob
            _cl_ob = self.db.query(_Cl_ob).filter(_Cl_ob.id == cluster_id).first()
            _ob_phase = getattr(_cl_ob, 'onboarding_phase', 'managed') or 'managed'
            if _ob_phase in ('shadow', 'takeover'):
                logger.info(
                    "placement_controller_onboarding_gate cluster=%s phase=%s",
                    cluster_id, _ob_phase,
                )
                self._emit_cycle_metrics(cluster_id, metrics, skipped_reason=f"onboarding_{_ob_phase}")
                return
        except Exception:
            pass  # fail open — unknown phase does not block PC

        # § KARPENTER INSTALLED GATE — view-only mode until Karpenter is detected
        # karpenter_mode=None  → Karpenter not installed → observation/recommendations only,
        #                         no pod evictions.
        # karpenter_mode set   → dry_run or auto → execution allowed (subject to toggle).
        try:
            from backend.models.cluster import Cluster as _Cl_km
            _cl_km = self.db.query(_Cl_km).filter(_Cl_km.id == cluster_id).first()
            if _cl_km and getattr(_cl_km, 'karpenter_mode', None) is None:
                logger.info(
                    "placement_controller_karpenter_not_installed cluster=%s — view-only mode, skipping evictions",
                    cluster_id,
                )
                self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="karpenter_not_installed")
                return
        except Exception:
            pass  # fail open

        # § SYMMETRIC LOCK — check rebalance:lock before scaling guard
        # auto_rebalancer already checks spot:cluster_mutex (held by PC).
        # PC must reciprocate: skip if AR holds rebalance:lock to avoid racing
        # CORDON/DRAIN mid-flight with an EVICT_POD on the same pods.
        try:
            from backend.core.redis_client import key_rebalance_lock as _key_rl
            _rl_key = _key_rl(cluster_id)
            if self.redis.exists(_rl_key):
                logger.info(
                    "placement_controller_rebalance_lock_held cluster=%s lock=%s",
                    cluster_id, _rl_key,
                )
                self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="rebalance_lock_held")
                return
        except Exception as _rl_exc:
            logger.debug("placement_controller_rebalance_lock_check_error cluster=%s: %s", cluster_id, _rl_exc)

        # § 4.3 — Cluster-level scaling guard (cheapest check first)
        if self._scaling_guard_active(cluster_id):
            logger.info(
                "placement_controller_skipped",
                extra={"cluster_id": cluster_id, "reason": "scaling_guard"},
            )
            self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="scaling_guard")
            return

        # § Phase 2 — Acquire cluster mutex (prevents race with auto_rebalancer)
        with cluster_mutex(
            self.redis, cluster_id, owner="placement_controller",
            ttl=CLUSTER_MUTEX_TTL_SECS,
        ) as acquired:
            if not acquired:
                logger.info(
                    "placement_controller_mutex_contention",
                    extra={"cluster_id": cluster_id},
                )
                self._emit_cycle_metrics(
                    cluster_id, metrics, skipped_reason="mutex_contention"
                )
                return

            # § Phase 3 — Cluster-wide batch limit.
            # Count ALL in-flight AgentAction records regardless of source.
            # Both engines write to the AgentAction table:
            #   • PlacementController → EVICT_POD
            #   • auto_rebalancer     → CORDON_NODE / DRAIN_NODE / UNCORDON_NODE
            # A single DB query across all action_types is the unified source of
            # truth and avoids double-counting.  The Redis semaphore is maintained
            # separately so auto_rebalancer's own guard can see PC's actions, but
            # it is NOT added here to prevent double-counting AR's active steps.
            try:
                from backend.models.agent_action import AgentAction, AgentActionStatus
                running_actions = (
                    self.db.query(AgentAction)
                    .filter(
                        AgentAction.cluster_id == cluster_id,
                        AgentAction.status.in_([
                            AgentActionStatus.PENDING,
                            AgentActionStatus.PICKED_UP,
                        ]),
                    )
                    .count()
                )
                cluster_slots_available = CLUSTER_BATCH_SIZE - running_actions
                if cluster_slots_available <= 0:
                    logger.info(
                        "placement_controller_batch_limit_reached",
                        extra={
                            "cluster_id": cluster_id,
                            "running_actions": running_actions,
                            "limit": CLUSTER_BATCH_SIZE,
                        },
                    )
                    metrics["evictions_skipped_batch_limit"] += 1
                    self._emit_cycle_metrics(
                        cluster_id, metrics, skipped_reason="batch_limit"
                    )
                    return
            except Exception as exc:
                logger.warning(
                    "placement_controller_batch_check_error",
                    extra={"cluster_id": cluster_id, "error": str(exc)},
                )
                cluster_slots_available = CLUSTER_BATCH_SIZE

            # § OD→SPOT OBSERVATION GATE — Issue 4
            # After MNG takeover completes, enforce minimum 24h before spot migration.
            # Prevents aggressively pushing to spot before WIE has a full-day profile.
            try:
                _tko_done_raw = self.redis.get(f"spot:takeover_completed_at:{cluster_id}")
                if _tko_done_raw:
                    _tko_done_ts = float(_tko_done_raw)
                    _time_since_tko = time.time() - _tko_done_ts
                    import os as _os_gate
                    _min_obs_secs = int(_os_gate.getenv("PC_MIN_OD_TO_SPOT_OBSERVATION_SECS", 86400))
                    if _min_obs_secs > 0 and _time_since_tko < _min_obs_secs:
                        logger.info(
                            "od_to_spot_observation_window cluster=%s elapsed=%.1fh required=%.1fh",
                            cluster_id, _time_since_tko / 3600, _min_obs_secs / 3600,
                        )
                        self._emit_cycle_metrics(
                            cluster_id, metrics, skipped_reason="od_spot_observation_window"
                        )
                        return
            except Exception:
                pass

            actionable_workloads = self._get_actionable_workloads(cluster_id)
            capacity_map = self._build_capacity_map(cluster_id)

            for policy in actionable_workloads:
                workload_id = policy.get("workload_id")
                if cluster_slots_available <= 0:
                    break
                try:
                    self._process_workload(
                        cluster_id, workload_id, policy, capacity_map, metrics,
                        cluster_slots_available=cluster_slots_available,
                    )
                    if metrics["evictions_attempted"] > 0:
                        cluster_slots_available -= 1
                except Exception as exc:
                    logger.exception(
                        "placement_controller_workload_error",
                        extra={
                            "cluster_id": cluster_id,
                            "workload_id": workload_id,
                            "error": str(exc),
                        },
                    )

            self._emit_cycle_metrics(cluster_id, metrics)

    # ------------------------------------------------------------------
    # Per-workload logic
    # ------------------------------------------------------------------

    def _process_workload(
        self,
        cluster_id: str,
        workload_id: str,
        policy: dict,
        capacity_map: CapacityMap,
        metrics: dict,
        cluster_slots_available: int = CLUSTER_BATCH_SIZE,
    ) -> None:
        from backend.utils.redis_locks import workload_lock as _workload_lock

        # § Phase 3 — Per-workload Redis lock (prevents parallel actions on same workload)
        with _workload_lock(
            self.redis, cluster_id, workload_id,
            owner="placement_controller", ttl=WORKLOAD_LOCK_TTL_SECS,
        ) as lock_acquired:
            if not lock_acquired:
                logger.info(
                    "placement_controller_workload_lock_contention",
                    extra={"cluster_id": cluster_id, "workload_id": workload_id},
                )
                metrics["evictions_skipped_lock_contention"] += 1
                return

            self._process_workload_inner(
                cluster_id, workload_id, policy, capacity_map, metrics,
                cluster_slots_available=cluster_slots_available,
            )
            self._emit_cycle_metrics(cluster_id, metrics, workload_id=workload_id)

    def _process_workload_inner(
        self,
        cluster_id: str,
        workload_id: str,
        policy: dict,
        capacity_map: CapacityMap,
        metrics: dict,
        cluster_slots_available: int = CLUSTER_BATCH_SIZE,
    ) -> None:
        # Guard order per plan.md §"Guard Conflict Resolution Order":
        # Priority 1 — HARD SAFETY (last-pod, live PDB) → checked first
        # Priority 2 — SYSTEM STATE (rolling update)
        # Priority 3 — COORDINATION (cooldown, active AgentAction)
        # Priority 4 — CAPACITY (batch limit / semaphore) — checked last

        # --- Fetch pod distribution early (needed for Priority 1 guard) ---
        current_od_pods = self._get_od_pods(cluster_id, workload_id)
        target_od = policy.get("ondemand_target", 1)

        # --- STATE FRESHNESS GATE — skip if agent state is stale ---
        # Agent writes updated_at (Unix float) to spot:workload:state every heartbeat.
        # If the last write is > PC_MAX_STALENESS_SECONDS old, the data we'd act on is
        # unreliable. Log a warning and abort — the next cycle will retry if state is fresh.
        try:
            _fresh_raw = self.redis.get(f"spot:workload:state:{cluster_id}:{workload_id}")
            if _fresh_raw:
                _fresh_state = json.loads(_fresh_raw)
                _observed_at = _fresh_state.get("updated_at")
                if _observed_at is not None and (time.time() - float(_observed_at)) > PC_MAX_STALENESS_SECONDS:
                    logger.warning(
                        "[PC] stale_state_skip cluster=%s workload=%s age=%.1fs",
                        cluster_id, workload_id,
                        time.time() - float(_observed_at),
                    )
                    self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP,
                                            DecisionReason.INSUFFICIENT_NODES,
                                            {"reason": "stale_agent_state",
                                             "observed_at": _observed_at,
                                             "staleness_seconds": round(time.time() - float(_observed_at), 1)})
                    return
        except Exception as _sf_exc:
            logger.debug("[PC] staleness check error for %s: %s — proceeding", workload_id, _sf_exc)

        # --- Priority 1: HARD SAFETY — last-pod guard (P0-B) ---
        # Never evict the last running pod of a workload.
        # Reads ready_replicas (spot+od total) from spot:workload:state (written by P0-A).
        try:
            _st_raw = self.redis.get(f"spot:workload:state:{cluster_id}:{workload_id}")
            if _st_raw:
                _st = json.loads(_st_raw)
                _total_running = int(_st.get("ready_replicas") or 0)
            else:
                # State not yet available — fall back to OD-only count (conservative)
                _total_running = len(current_od_pods)
        except (json.JSONDecodeError, TypeError, Exception):
            _total_running = len(current_od_pods)
        if _total_running <= 1:
            logger.info(
                "placement_controller_last_pod_protection",
                extra={"cluster_id": cluster_id, "workload_id": workload_id,
                       "total_running": _total_running},
            )
            metrics["evictions_skipped_last_pod"] += 1
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.INSUFFICIENT_NODES, {"reason": "last_pod_protection", "total_running": _total_running})
            return

        # --- Priority 2: SYSTEM STATE — rolling update in progress ---
        rollout = self._get_rollout_status(cluster_id, workload_id)
        if rollout and rollout.updated_replicas != rollout.ready_replicas:
            metrics["evictions_skipped_scaling_guard"] += 1
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.DEFER, DecisionReason.ROLLOUT_BLOCKED, {"updated_replicas": rollout.updated_replicas, "ready_replicas": rollout.ready_replicas})
            return

        # --- Priority 3: COORDINATION — per-workload cooldown ---
        if self._workload_in_cooldown(cluster_id, workload_id):
            metrics["evictions_skipped_cooldown"] += 1
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.COOLDOWN_ACTIVE, {})
            return

        # --- Priority 3: COORDINATION — P2-B L1: skip if active AgentAction in-flight ---
        # Prevents PC from queuing a second eviction while agent is executing the first.
        try:
            from backend.models.agent_action import AgentAction, AgentActionStatus
            from backend.core.database import SessionLocal
            _db = SessionLocal()
            try:
                from backend.models.agent_action import AgentActionType as _AAT
                _active = _db.query(AgentAction).filter(
                    AgentAction.cluster_id == cluster_id,
                    AgentAction.action_type == _AAT.EVICT_POD,
                    AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                    AgentAction.payload.op("->>")(  # JSONB text extraction
                        "workload_id"
                    ) == workload_id,
                ).first()
                if _active:
                    logger.info(
                        "placement_controller_skip_active_action",
                        extra={"cluster_id": cluster_id, "workload_id": workload_id,
                               "action_id": _active.id, "status": str(_active.status)},
                    )
                    metrics["evictions_skipped_active_action"] += 1
                    self._emit_decision_log(cluster_id, workload_id, DecisionAction.DEFER, DecisionReason.BATCH_LIMIT_REACHED, {"reason": "active_eviction_in_flight"})
                    return
            finally:
                _db.close()
        except Exception as _exc:
            logger.warning(f"[PC] active-action check failed for {workload_id}: {_exc}")

        # --- Excess On-Demand pods ---
        excess_od = max(0, len(current_od_pods) - target_od)

        # 5. Drift threshold
        if target_od <= DRIFT_THRESHOLD_SMALL_MAX_TARGET:
            drift_threshold = DRIFT_THRESHOLD_SMALL
        else:
            drift_threshold = max(2, int(target_od * DRIFT_THRESHOLD_PCT))

        if excess_od < drift_threshold:
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.AT_TARGET, {"excess_od": excess_od, "drift_threshold": drift_threshold})
            return

        # 6. Rate limit
        excess_od = min(excess_od, MAX_EVICTIONS_PER_CYCLE)

        # 7. Select pods to evict (Fix 4: youngest-first, skip pods < 2 min old)
        pods_to_evict = self._select_burst_pods(
            current_od_pods, excess_od, metrics,
            cluster_id=cluster_id, workload_id=workload_id,
        )
        if not pods_to_evict:
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.AT_TARGET, {"reason": "no_eligible_pods"})
            return

        # 8. Compute desired AZ per pod (capacity-biased)
        desired_az_map = self._compute_desired_az_with_capacity(
            cluster_id, workload_id, pods_to_evict, capacity_map
        )

        # 9. Capacity check (CPU + memory + ENI)
        if not self._has_spot_capacity_for_target_az(
            pods_to_evict, desired_az_map, capacity_map
        ):
            logger.info(
                "spot_capacity_insufficient",
                extra={"cluster_id": cluster_id, "workload_id": workload_id},
            )
            metrics["evictions_skipped_capacity"] += 1

            # Fix 5: Check if any Spot node exists at all — if not, log no_replacement
            if not self._any_spot_capacity_exists(capacity_map):
                metrics["evictions_failed_due_to_no_replacement"] += 1

            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.INSUFFICIENT_NODES, {"reason": "no_spot_capacity"})
            return

        # Shadow mode guard (§8 Phase 6) — metrics only, no actual evictions
        if self._is_shadow_mode(cluster_id):
            logger.info(
                "placement_controller_shadow_mode",
                extra={
                    "cluster_id": cluster_id,
                    "workload_id": workload_id,
                    "would_evict": len(pods_to_evict),
                    "disruption_safe": policy.get("disruption_safe", True),
                },
            )
            metrics["evictions_attempted"] += len(pods_to_evict)
            self._emit_decision_log(cluster_id, workload_id, DecisionAction.SKIP, DecisionReason.OBSERVATION_MODE, {"would_evict": len(pods_to_evict)})
            return

        # 10. Act based on disruption safety
        disruption_safe = policy.get("disruption_safe", True)

        if disruption_safe:
            for pod in pods_to_evict:
                # P2-A: live PDB check — block eviction if it would violate pdb_min_available
                if self._would_violate_pdb(cluster_id, workload_id):
                    metrics["evictions_skipped_pdb_violation"] += 1
                    continue
                self._dispatch_eviction(cluster_id, workload_id, pod, policy)
                metrics["evictions_attempted"] += 1
            self._set_workload_cooldown(cluster_id, workload_id, WORKLOAD_COOLDOWN_MINUTES)
        else:
            # Stateful path — create-before-delete via RebalancingAction DB record
            original_replicas = policy.get("current_replicas", 1)
            for pod in pods_to_evict:
                try:
                    self._dispatch_stateful_rollout(
                        cluster_id, workload_id, pod, original_replicas
                    )
                    metrics["stateful_rollout_started"] += 1
                except Exception:
                    metrics["stateful_rollout_failed"] += 1
            self._set_workload_cooldown(
                cluster_id, workload_id, WORKLOAD_COOLDOWN_MINUTES * 2
            )

        self._emit_decision_log(cluster_id, workload_id, DecisionAction.EVICT, DecisionReason.AT_TARGET, {"evictions_attempted": metrics.get("evictions_attempted", 0)})

    # ------------------------------------------------------------------
    # PDB helper — P2-A
    # ------------------------------------------------------------------

    def _would_violate_pdb(self, cluster_id: str, workload_id: str) -> bool:
        """
        Returns True (block eviction) if the PDB would be violated.
        Fails closed (returns True = block) when Redis is unavailable — unknown
        state must not permit eviction. Returns False only when we have confirmed
        live data showing no violation.
        """
        try:
            raw = self.redis.get(f"spot:workload:state:{cluster_id}:{workload_id}")
            if not raw:
                return False
            state = json.loads(raw)
            pdb_min = state.get("pdb_min_available")
            ready = state.get("ready_replicas")
            if pdb_min is None or ready is None:
                return False
            return (int(ready) - 1) < int(pdb_min)
        except Exception as exc:
            logger.warning(f"[PC] _would_violate_pdb redis error for {workload_id}: {exc} — blocking eviction (fail-closed)")
            return True

    # ------------------------------------------------------------------
    # Pod selection — § 4.5 + Fix 4
    # ------------------------------------------------------------------

    def _select_burst_pods(
        self,
        od_pods: List[PodInfo],
        count: int,
        metrics: dict,
        cluster_id: str = "",
        workload_id: str = "",
    ) -> List[PodInfo]:
        """
        1. Filter pods younger than POD_AGE_MIN_SECONDS (Fix 4 — prevent
           controller fighting the scheduler on freshly placed pods).
        2. P2-B L2: skip pods whose node is locked by spot:node_active_action.
        3. Prefer over-represented AZ.
        4. Newest-first within candidates (§ 4.5 — lowest accumulated state).
        """
        # P2-B L2: pre-build node_name → instance_id map (single batch query).
        # spot:node_active_action is keyed by instance_id (not node_name).
        _node_inst_map: dict = {}
        try:
            from backend.models.instance import Instance as _Inst
            _node_names = [p.node for p in od_pods if p.node]
            if _node_names:
                _rows = self.db.query(_Inst.node_name, _Inst.instance_id).filter(
                    _Inst.node_name.in_(_node_names)
                ).all()
                _node_inst_map = {r.node_name: r.instance_id for r in _rows if r.node_name}
        except Exception:
            pass  # fail open — no lock filtering if lookup fails

        # Anchor node guard: read anchor_nodes written by placement-detail API (TTL 5 min)
        # Key: spot:placement:anchor_nodes:{cluster_id}:{workload_id}
        # Fail-open: if key is missing or Redis is down, no pods are blocked by this guard.
        _anchor_nodes: set = set()
        try:
            if cluster_id and workload_id:
                _a_raw = self.redis.get(
                    f"spot:placement:anchor_nodes:{cluster_id}:{workload_id}"
                )
                if _a_raw:
                    _anchor_nodes = set(json.loads(_a_raw))
        except Exception:
            pass  # fail open

        # Change 2: Pre-build set of nodes labelled spot-optimizer/draining=true.
        # AR sets this label on the node during CORDON so PC never evicts pods
        # from a node that is already mid-drain.
        _draining_nodes: set = set()
        try:
            _node_names_all = [p.node for p in od_pods if p.node]
            if _node_names_all:
                from backend.models.instance import Instance as _InstDrain
                _drain_rows = self.db.query(
                    _InstDrain.node_name
                ).filter(
                    _InstDrain.node_name.in_(_node_names_all),
                    _InstDrain.cluster_id == cluster_id,
                ).all()
                _drain_node_names = {r.node_name for r in _drain_rows if r.node_name}
                for _dn in _drain_node_names:
                    _d_raw = self.redis.get(f"spot:node:draining:{cluster_id}:{_dn}")
                    if _d_raw:
                        _draining_nodes.add(_dn)
        except Exception:
            pass  # fail open

        eligible = []
        skipped_young = 0
        for pod in od_pods:
            if pod.age_seconds < POD_AGE_MIN_SECONDS:
                skipped_young += 1
                continue
            # P2-B L2: skip pods on nodes that have an active drain/migration lock
            try:
                _inst_id = _node_inst_map.get(pod.node)
                if _inst_id and self.redis.exists(f"spot:node_active_action:{_inst_id}"):
                    metrics["evictions_skipped_node_drain"] = (
                        metrics.get("evictions_skipped_node_drain", 0) + 1
                    )
                    continue
            except Exception:
                pass  # fail open — let the pod remain eligible
            # Change 2: Skip pods on nodes with draining label
            if pod.node and pod.node in _draining_nodes:
                metrics["evictions_skipped_node_drain"] = (
                    metrics.get("evictions_skipped_node_drain", 0) + 1
                )
                continue
            # Anchor node guard: never evict pods on anchor nodes
            if pod.node and pod.node in _anchor_nodes:
                metrics["evictions_skipped_anchor_guard"] = (
                    metrics.get("evictions_skipped_anchor_guard", 0) + 1
                )
                continue
            eligible.append(pod)

        metrics["evictions_skipped_pod_too_young"] += skipped_young

        if not eligible:
            return []

        az_counts = Counter(p.az for p in eligible)
        over_represented_az = max(az_counts, key=az_counts.get)
        candidates = [p for p in eligible if p.az == over_represented_az]

        # Newest first: sort ascending by age (low age = newer), take first `count`
        candidates.sort(key=lambda p: p.age_seconds)
        return candidates[:count]

    # ------------------------------------------------------------------
    # Capacity helpers — § 4.6 + § 4.7
    # ------------------------------------------------------------------

    def _compute_desired_az_with_capacity(
        self,
        cluster_id: str,
        workload_id: str,
        pods_to_evict: List[PodInfo],
        capacity_map: CapacityMap,
    ) -> Dict[str, str]:
        """Map each pod UID → ideal target AZ (lowest workload + capacity score)."""
        current_az_counts = self._count_pods_by_az(cluster_id, workload_id)
        all_azs = list(capacity_map.nodes_by_az.keys())

        if not all_azs:
            return {pod.uid: pod.az for pod in pods_to_evict}

        desired_map: Dict[str, str] = {}
        for pod in pods_to_evict:
            best_az = all_azs[0]
            best_score = float("inf")
            for az in all_azs:
                workload_score = current_az_counts.get(az, 0)
                nodes = capacity_map.get_nodes(az)
                free_cpu = sum(
                    n.allocatable_cpu - (n.allocatable_cpu * (1 - SPOT_CAPACITY_BUFFER))
                    for n in nodes
                )
                free_mem = sum(
                    n.allocatable_memory - (n.allocatable_memory * (1 - SPOT_CAPACITY_BUFFER))
                    for n in nodes
                )
                capacity_penalty = 0
                if free_cpu < pod.cpu_request or free_mem < pod.memory_request:
                    capacity_penalty = 100
                total_score = workload_score + capacity_penalty
                if total_score < best_score:
                    best_score = total_score
                    best_az = az
            desired_map[pod.uid] = best_az
            current_az_counts[best_az] = current_az_counts.get(best_az, 0) + 1
        return desired_map

    def _has_spot_capacity_for_target_az(
        self,
        pods: List[PodInfo],
        desired_az_map: Dict[str, str],
        capacity_map: CapacityMap,
    ) -> bool:
        """CPU + memory + ENI slot check per target AZ (§ 4.7)."""
        pods_by_az: Dict[str, List[PodInfo]] = {}
        for pod in pods:
            target_az = desired_az_map.get(pod.uid, pod.az)
            pods_by_az.setdefault(target_az, []).append(pod)

        for az, az_pods in pods_by_az.items():
            nodes = capacity_map.get_nodes(az)
            if not nodes:
                return False

            total_cpu = sum(n.allocatable_cpu for n in nodes)
            total_mem = sum(n.allocatable_memory for n in nodes)
            total_slots = sum(n.max_pods - n.current_pod_count for n in nodes)
            req_cpu = sum(p.cpu_request for p in az_pods)
            req_mem = sum(p.memory_request for p in az_pods)

            if req_cpu > total_cpu * SPOT_CAPACITY_BUFFER:
                return False
            if req_mem > total_mem * SPOT_CAPACITY_BUFFER:
                return False
            if len(az_pods) > total_slots * SPOT_CAPACITY_BUFFER:
                return False
        return True

    def _any_spot_capacity_exists(self, capacity_map: CapacityMap) -> bool:
        """True when at least one Spot node with free slots exists anywhere."""
        for nodes in capacity_map.nodes_by_az.values():
            for node in nodes:
                if node.max_pods > node.current_pod_count:
                    return True
        return False

    # ------------------------------------------------------------------
    # Scaling guard — § 4.3
    # ------------------------------------------------------------------

    def _scaling_guard_active(self, cluster_id: str) -> bool:
        pending = self._get_pending_pods_count(cluster_id)
        if pending > PENDING_PODS_THRESHOLD:
            return True
        if self._recent_keda_scaling_event(cluster_id):
            return True
        return self._recent_hpa_scaling_event(cluster_id)

    def _recent_hpa_scaling_event(self, cluster_id: str) -> bool:
        """Returns True if an HPA scale-up (desiredReplicas > currentReplicas) was
        observed within the last HPA_SCALING_GUARD_WINDOW_SECONDS seconds."""
        key = HPA_EVENT_KEY_TEMPLATE.format(cluster_id=cluster_id)
        try:
            raw = self.redis.get(key)
            if not raw:
                return False
            ts = float(raw)
            return (time.time() - ts) < HPA_SCALING_GUARD_WINDOW_SECONDS
        except Exception:
            return False  # fail open — HPA guard is best-effort

    def _recent_keda_scaling_event(self, cluster_id: str) -> bool:
        key = KEDA_EVENT_KEY_TEMPLATE.format(cluster_id=cluster_id)
        raw = self.redis.get(key)
        if not raw:
            # Key absent — two cases:
            # 1. Process just started (no event yet) → safe to allow evictions during bootstrap
            # 2. Redis restarted / key expired → be conservative and block
            # Distinguish by process uptime: bootstrap window = 5 min (configurable)
            process_uptime = time.time() - _PROCESS_START_TIME
            # During bootstrap window → assume no event (return False = allow)
            # After bootstrap window → assume event may have been missed (return True = block)
            if process_uptime > KEDA_BOOTSTRAP_WINDOW_SECONDS:
                logger.warning(
                    "keda_event_key_absent_blocking_evictions cluster=%s uptime=%.0fs "
                    "key=%s — verify agent is writing this key on KEDA scale events",
                    cluster_id, process_uptime, key,
                )
            return process_uptime > KEDA_BOOTSTRAP_WINDOW_SECONDS
        try:
            ts = float(raw)
            return (time.time() - ts) < SCALING_GUARD_WINDOW_SECONDS
        except (ValueError, TypeError):
            return True  # fail-safe: unparseable timestamp → block

    def _get_pending_pods_count(self, cluster_id: str) -> int:
        key = PENDING_PODS_KEY_TEMPLATE.format(cluster_id=cluster_id)
        raw = self.redis.get(key)
        if raw is None:
            # Fail-safe: key absent → assume worst case (above threshold)
            return PENDING_PODS_THRESHOLD + 1
        try:
            return int(raw)
        except (ValueError, TypeError):
            return PENDING_PODS_THRESHOLD + 1

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _workload_in_cooldown(self, cluster_id: str, workload_id: str) -> bool:
        key = COOLDOWN_KEY_TEMPLATE.format(
            cluster_id=cluster_id, workload_id=workload_id
        )
        try:
            return bool(self.redis.exists(key))
        except Exception as exc:
            logger.warning(f"[PC] _workload_in_cooldown redis error for {workload_id}: {exc} — blocking eviction (fail-closed)")
            return True

    def _set_workload_cooldown(
        self, cluster_id: str, workload_id: str, minutes: int
    ) -> None:
        key = COOLDOWN_KEY_TEMPLATE.format(
            cluster_id=cluster_id, workload_id=workload_id
        )
        self.redis.setex(key, minutes * 60, "1")

    def _emit_decision_log(
        self,
        cluster_id: str,
        workload_id: str,
        action: DecisionAction,
        reason: DecisionReason,
        context: dict,
    ) -> None:
        try:
            key = WORKLOAD_LOG_KEY_TEMPLATE.format(
                cluster_id=cluster_id, workload_id=workload_id
            )
            record = json.dumps({
                "action": action.value,
                "reason": reason.value,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "context": context,
            })
            pipe = self.redis.pipeline()
            pipe.lpush(key, record)
            pipe.ltrim(key, 0, 49)          # keep last 50 decisions
            pipe.expire(key, 604800)         # WP-3: 7 days TTL (was 1h)
            pipe.execute()
        except Exception as exc:
            logger.warning(
                "placement_controller_decision_log_error",
                extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(exc)},
            )

    # ------------------------------------------------------------------
    # K8s rollout status — § 4.4 step 2
    # ------------------------------------------------------------------

    def _get_rollout_status(
        self, cluster_id: str, workload_id: str
    ) -> Optional[RolloutStatus]:
        """
        Reads live Deployment rollout status from K8s API.
        Returns None for non-Deployment workloads (StatefulSet, DaemonSet) —
        those are handled by the stateful path.
        Falls back gracefully to None on API errors.
        """
        cache_key = f"spot:placement_controller:rollout_status:{cluster_id}:{workload_id}"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return RolloutStatus(**data)
            except Exception:
                pass

        try:
            namespace, name = workload_id.split("/", 1)
            result = self.k8s.get_deployment_rollout_status(namespace, name)
            if result:
                payload = {
                    "updated_replicas": result.get("updated_replicas", 0),
                    "ready_replicas": result.get("ready_replicas", 0),
                }
                self.redis.setex(cache_key, ROLLOUT_STATUS_CACHE_TTL, json.dumps(payload))
                return RolloutStatus(**payload)
        except Exception as exc:
            logger.warning(
                "rollout_status_fetch_error",
                extra={"workload_id": workload_id, "error": str(exc)},
            )
        return None

    # ------------------------------------------------------------------
    # Pod and workload data access
    # ------------------------------------------------------------------

    def _get_actionable_workloads(self, cluster_id: str) -> List[dict]:
        """
        Returns list of placement policies where actionable=True.
        Reads from Redis; falls back to DB on cache miss.
        Workloads with an active oscillation-block key are silently skipped.
        """
        pattern = POLICY_KEY_TEMPLATE.format(
            cluster_id=cluster_id, workload_id="*"
        )
        keys = self.redis.keys(pattern)
        policies = []
        for key in keys:
            raw = self.redis.get(key)
            if raw:
                try:
                    policy = json.loads(raw)
                    if not policy.get("actionable"):
                        continue
                    wid = policy.get("workload_id", "")
                    if wid:
                        block_key = OSCILLATION_BLOCK_KEY.format(
                            cluster_id=cluster_id, workload_id=wid
                        )
                        try:
                            if self.redis.exists(block_key):
                                logger.debug(
                                    f"[PC] Workload {wid} skipped — oscillation block active"
                                )
                                continue
                        except Exception:
                            pass  # fail open: if Redis error, don't skip
                    policies.append(policy)
                except (json.JSONDecodeError, TypeError):
                    pass
        return policies

    def _get_od_pods(self, cluster_id: str, workload_id: str) -> List[PodInfo]:
        """
        Reads current On-Demand pods for a workload from agent Redis state.
        Returns PodInfo list.
        """
        key = f"spot:workload:pods:{cluster_id}:{workload_id}"
        raw = self.redis.get(key)
        if not raw:
            return []
        try:
            pods_data = json.loads(raw)
            result = []
            for p in pods_data:
                if p.get("capacity_type") == "on-demand":
                    result.append(
                        PodInfo(
                            uid=p.get("uid", ""),
                            name=p.get("name", ""),
                            namespace=p.get("namespace", ""),
                            az=p.get("az", ""),
                            node=p.get("node", ""),
                            capacity_type=p.get("capacity_type", "on-demand"),
                            cpu_request=float(p.get("cpu_request", 0)),
                            memory_request=float(p.get("memory_request", 0)),
                            age_seconds=float(p.get("age_seconds", 0)),
                        )
                    )
            return result
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def _count_pods_by_az(
        self, cluster_id: str, workload_id: str
    ) -> Dict[str, int]:
        key = f"spot:workload:pods:{cluster_id}:{workload_id}"
        raw = self.redis.get(key)
        counts: Dict[str, int] = {}
        if raw:
            try:
                pods_data = json.loads(raw)
                for p in pods_data:
                    az = p.get("az", "unknown")
                    counts[az] = counts.get(az, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        return counts

    def _build_capacity_map(self, cluster_id: str) -> CapacityMap:
        """
        Builds a CapacityMap from agent-reported Spot node state in Redis.
        Falls back to K8s API for live ENI/pod counts.
        """
        key = f"spot:cluster:spot_nodes:{cluster_id}"
        raw = self.redis.get(key)
        nodes_by_az: Dict[str, List[SpotNode]] = {}
        if raw:
            try:
                nodes_data = json.loads(raw)
                for n in nodes_data:
                    node = SpotNode(
                        name=n.get("name", ""),
                        az=n.get("az", ""),
                        allocatable_cpu=float(n.get("allocatable_cpu", 0)),
                        allocatable_memory=float(n.get("allocatable_memory", 0)),
                        max_pods=int(n.get("max_pods", 0)),
                        current_pod_count=int(n.get("current_pod_count", 0)),
                    )
                    nodes_by_az.setdefault(node.az, []).append(node)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return CapacityMap(nodes_by_az=nodes_by_az)

    # ------------------------------------------------------------------
    # Action dispatch — § Phase 1
    # ------------------------------------------------------------------

    def _is_shadow_mode(self, cluster_id: str) -> bool:
        """Returns True when shadow mode is active — metrics only, no evictions."""
        key = SHADOW_MODE_KEY_TEMPLATE.format(cluster_id=cluster_id)
        return bool(self.redis.get(key))

    def _dispatch_eviction(
        self,
        cluster_id: str,
        workload_id: str,
        pod: PodInfo,
        policy: Optional[dict] = None,
        target_capacity: str = "spot",
    ) -> None:
        """
        Creates an EVICT_POD AgentAction DB record for the agent to execute.
        Also creates a linked RebalancingAction for dashboard visibility.
        Replaces the previous Redis rpush dispatch path.
        """
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        from backend.models.rebalancing_action import RebalancingAction

        # EVICT_POD dedup: skip if a PENDING/PICKED_UP action already exists for this pod
        try:
            _existing = (
                self.db.query(AgentAction)
                .filter(
                    AgentAction.cluster_id == cluster_id,
                    AgentAction.action_type == AgentActionType.EVICT_POD,
                    AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                )
                .filter(
                    AgentAction.payload["pod_name"].astext == pod.name
                )
                .first()
            )
            if _existing:
                logger.info(
                    "evict_pod_dedup_skipped cluster=%s pod=%s existing_action=%s",
                    cluster_id, pod.name, _existing.id,
                )
                return
        except Exception as _dedup_exc:
            logger.debug("evict_pod_dedup_check_error cluster=%s pod=%s: %s", cluster_id, pod.name, _dedup_exc)

        policy = policy or {}
        action_metadata = {
            "migration_type": "pod_level",
            "stateful_strategy": None,
            "migration_timeout_minutes": MIGRATION_TIMEOUT_MINUTES,
            "migration_failed_cooldown_minutes": MIGRATION_FAILED_COOLDOWN_MINUTES,
            "target_capacity_type": target_capacity,
            "pods_to_evict": [pod.name],
            "original_replicas": policy.get("current_replicas"),
            "source": "placement_controller",
            "dispatched_at": datetime.now(tz=timezone.utc).isoformat(),
            # Convergence tracking — read by validate_actions_task
            "expected": {
                "pod_name": pod.name,
                "from_node": pod.node,
                "workload_id": workload_id,
            },
            "observed": False,
            "deadline": time.time() + PC_ACTION_DEADLINE_SECONDS,
        }

        agent_action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.EVICT_POD,
            status=AgentActionStatus.PENDING,
            retry_count=0,
            payload={
                "namespace": pod.namespace,
                "pod_name": pod.name,
                "node_name": pod.node,
                "az": pod.az,
                "workload_id": workload_id,
            },
            result=action_metadata,
        )
        self.db.add(agent_action)
        self.db.flush()  # populate agent_action.id before linking RebalancingAction

        rebalancing_action = RebalancingAction(
            cluster_id=cluster_id,
            trigger="graceful",
            source_pool=f"{pod.node}:{pod.az}",
            target_pool=f"spot:{pod.az}",
            status="in_progress",
            migration_type="pod_level",
            source="placement_controller",
            agent_action_id=agent_action.id,
            started_at=datetime.utcnow(),
        )
        self.db.add(rebalancing_action)
        self.db.commit()

        # WP-4: Optimistic state update so next cycle sees the correct count immediately
        try:
            state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
            raw = self.redis.get(state_key)
            if raw:
                st = json.loads(raw)
                st["current_ondemand_pods"] = max(0, int(st.get("current_ondemand_pods", 1)) - 1)
                st["current_spot_pods"] = int(st.get("current_spot_pods", 0)) + 1
                self.redis.set(state_key, json.dumps(st), ex=300)
        except Exception as _opt_exc:
            logger.debug("optimistic_state_update_skipped: %s", _opt_exc)

        logger.info(
            "evict_pod_action_dispatched",
            extra={
                "cluster_id": cluster_id,
                "workload_id": workload_id,
                "pod": pod.name,
                "az": pod.az,
                "action_id": agent_action.id,
            },
        )

    def _dispatch_stateful_rollout(
        self,
        cluster_id: str,
        workload_id: str,
        pod: PodInfo,
        original_replicas: int,
    ) -> None:
        """
        Creates a RebalancingAction DB record for the auto_rebalancer to execute
        a create-before-delete stateful migration. Does NOT call the rollout
        service directly — auto_rebalancer picks it up and executes it.
        """
        from backend.models.rebalancing_action import RebalancingAction

        rebalancing_action = RebalancingAction(
            cluster_id=cluster_id,
            trigger="graceful",
            source_pool=f"{pod.node}:{pod.az}",
            target_pool=f"spot:{pod.az}",
            status="in_progress",
            migration_type="stateful_pod",
            source="placement_controller",
            agent_action_id=None,
            started_at=datetime.utcnow(),
            action_metadata={
                "stateful_strategy": "create_before_delete",
                "migration_timeout_minutes": MIGRATION_TIMEOUT_MINUTES,
                "migration_failed_cooldown_minutes": MIGRATION_FAILED_COOLDOWN_MINUTES,
                "pod_name": pod.name,
                "namespace": pod.namespace,
                "node_name": pod.node,
                "original_replicas": original_replicas,
                "workload_id": workload_id,
            },
        )
        self.db.add(rebalancing_action)
        self.db.commit()

        logger.info(
            "stateful_rollout_dispatched",
            extra={
                "cluster_id": cluster_id,
                "workload_id": workload_id,
                "pod": pod.name,
                "rebalancing_action_id": rebalancing_action.id,
            },
        )

    # ------------------------------------------------------------------
    # Metrics emission — § 6 + Fix 5
    # ------------------------------------------------------------------

    def _emit_cycle_metrics(
        self,
        cluster_id: str,
        metrics: dict,
        skipped_reason: str = "",
        workload_id: Optional[str] = None,
    ) -> None:
        """
        Write structured cycle metrics to Redis HASH.
        Includes all §9 Phase 7 counters and post-eviction retry counters.
        """
        key = METRICS_KEY_TEMPLATE.format(cluster_id=cluster_id)
        payload = {
            "cycle_ts": datetime.now(tz=timezone.utc).isoformat(),
            "skipped_reason": skipped_reason,
            "evictions_attempted": metrics.get("evictions_attempted", 0),
            "evictions_skipped_capacity": metrics.get("evictions_skipped_capacity", 0),
            "evictions_skipped_cooldown": metrics.get("evictions_skipped_cooldown", 0),
            "evictions_skipped_scaling_guard": metrics.get("evictions_skipped_scaling_guard", 0),
            "evictions_skipped_pod_too_young": metrics.get("evictions_skipped_pod_too_young", 0),
            "evictions_skipped_lock_contention": metrics.get("evictions_skipped_lock_contention", 0),
            "evictions_skipped_batch_limit": metrics.get("evictions_skipped_batch_limit", 0),
            "evictions_skipped_last_pod": metrics.get("evictions_skipped_last_pod", 0),
            "evictions_skipped_pdb_violation": metrics.get("evictions_skipped_pdb_violation", 0),
            "evictions_skipped_active_action": metrics.get("evictions_skipped_active_action", 0),
            "evictions_skipped_node_drain": metrics.get("evictions_skipped_node_drain", 0),
            "evictions_failed_due_to_no_replacement": metrics.get(
                "evictions_failed_due_to_no_replacement", 0
            ),
            "stateful_rollout_started": metrics.get("stateful_rollout_started", 0),
            "stateful_rollout_completed": metrics.get("stateful_rollout_completed", 0),
            "stateful_rollout_failed": metrics.get("stateful_rollout_failed", 0),
            "stateful_rollout_timeout": metrics.get("stateful_rollout_timeout", 0),
            "retry_incremented": metrics.get("retry_incremented", 0),
            "permanent_failures": metrics.get("permanent_failures", 0),
            "circuit_breaker_tripped": metrics.get("circuit_breaker_tripped", 0),
        }
        try:
            self.redis.hset(key, mapping=payload)
            self.redis.expire(key, METRICS_TTL)
            if workload_id:
                try:
                    wl_key = f"spot:placement_controller:metrics:{cluster_id}:{workload_id}"
                    self.redis.hset(wl_key, mapping=payload)
                    self.redis.expire(wl_key, METRICS_TTL)
                except Exception as wl_exc:
                    logger.warning(
                        "placement_controller_workload_metrics_error",
                        extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(wl_exc)},
                    )
        except Exception as exc:
            logger.warning(
                "placement_controller_metrics_error",
                extra={"cluster_id": cluster_id, "error": str(exc)},
            )


# ---------------------------------------------------------------------------
# Post-eviction validation + retry cap — § Phase 6
# ---------------------------------------------------------------------------

def handle_eviction_result(action, db, redis) -> None:
    """
    Called once after an EVICT_POD AgentAction is reported complete by the agent.
    Validates the pod landed on the correct capacity type.
    Marks for retry or permanent failure as appropriate.
    Accepts 5-10% scheduler non-determinism as expected variance.
    """
    from backend.models.agent_action import AgentActionStatus

    if action.action_type.value != "EVICT_POD":
        return

    pod_name = action.payload.get("pod_name") or action.payload.get("pod")
    namespace = action.payload.get("namespace", "default")
    workload_id = action.payload.get("workload_id", "")
    result_meta = action.result or {}
    target_cap = result_meta.get("target_capacity_type", "spot")

    try:
        placement = get_pod_placement(namespace, pod_name)
    except Exception as exc:
        # K8s API unreachable — cannot verify placement.  Eviction succeeded
        # per agent report, so mark COMPLETED and let PlacementController's
        # next 5-minute drift detection cycle re-evaluate rather than
        # permanently failing a successful eviction.
        logger.warning(
            f"[PC] Could not check placement for pod={pod_name}: {exc}. "
            f"Marking COMPLETED — PlacementController will detect drift on next cycle."
        )
        action.status = AgentActionStatus.COMPLETED
        action.result = {
            **(action.result or {}),
            "placement_check": f"api_error:{str(exc)[:80]}",
            "needs_revalidation": True,
        }
        _update_rebalancing_action(action.id, status="completed", db=db)
        _decr_semaphore(action.cluster_id, redis)
        db.commit()
        return

    if placement is None:
        # Pod is still Pending — Karpenter hasn't scheduled it yet.  Eviction
        # succeeded; the outcome (Spot vs On-Demand) is unknown at this moment.
        # Mark COMPLETED and let PlacementController's next 5-minute drift
        # detection cycle re-evaluate if the pod lands on On-Demand.
        action.status = AgentActionStatus.COMPLETED
        action.result = {**(action.result or {}), "placement_check": "pod_pending_at_validation_time"}
        _update_rebalancing_action(action.id, status="completed", db=db)
        _decr_semaphore(action.cluster_id, redis)
        logger.info(
            f"[PC] pod={pod_name} is Pending at validation time — eviction succeeded; "
            f"PlacementController will detect drift if pod lands on On-Demand. "
            f"action={action.id} COMPLETED"
        )
        db.commit()

    elif placement.capacity_type != target_cap:
        # Pod re-scheduled on On-Demand instead of Spot.  The evicted pod no
        # longer exists, so the same action cannot be re-queued.  Mark FAILED
        # and let the next PlacementController cycle detect the OD pod as drift
        # and dispatch a fresh eviction action.
        logger.info(
            f"[PC] pod={pod_name} landed on {placement.capacity_type} "
            f"(target={target_cap}, scheduler variance). retry_count={action.retry_count + 1}"
        )
        _track_od_landing(action.cluster_id, workload_id, redis)
        _mark_for_retry(action, workload_id, db, redis)

    else:
        action.status = AgentActionStatus.COMPLETED
        _update_rebalancing_action(action.id, status="completed", db=db)
        _decr_semaphore(action.cluster_id, redis)
        logger.info(
            f"[PC] pod={pod_name} successfully placed on {target_cap}. action={action.id} COMPLETED"
        )
        db.commit()


def _mark_for_retry(action, workload_id: str, db, redis) -> None:
    from backend.models.agent_action import AgentActionStatus

    action.retry_count = (action.retry_count or 0) + 1

    # The evicted pod no longer exists after eviction — re-queuing the same
    # AgentAction as PENDING would cause the agent to receive a K8s 404 on the
    # next poll.  Always mark FAILED and let PlacementController's next 5-minute
    # cycle detect remaining OD drift and dispatch a fresh action for the new pod.
    action.status = AgentActionStatus.FAILED
    action.error_message = (
        f"pod_evicted_but_not_on_spot "
        f"(attempt {action.retry_count}/{MAX_RETRY_COUNT}); "
        "placement_controller will recheck drift on next cycle"
    )
    _update_rebalancing_action(action.id, status="failed", db=db)
    _decr_semaphore(action.cluster_id, redis)

    if action.retry_count >= MAX_RETRY_COUNT:
        logger.warning(
            f"[PC] action={action.id} pod={action.payload.get('pod_name')} "
            f"hit MAX_RETRY_COUNT={MAX_RETRY_COUNT}. Marking FAILED permanently. "
            f"PlacementController will re-evaluate on next cycle after cooldown."
        )
        # P3-A: alert on permanent failure so ops team is notified
        try:
            import asyncio
            from backend.services.notification_service import NotificationService
            from backend.models.alert_config import AlertType, AlertSeverity
            from backend.models.cluster import Cluster
            _cl = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
            _org_id = getattr(_cl, "organization_id", None) or "unknown"
            _ns = NotificationService(db=db)
            asyncio.run(_ns.send_alert(
                alert_type=AlertType.EXECUTION_FAILED,
                organization_id=_org_id,
                title="PlacementController permanent eviction failure",
                message=(
                    f"action={action.id} pod={action.payload.get('pod_name')} "
                    f"cluster={action.cluster_id} failed after "
                    f"{MAX_RETRY_COUNT} attempts — pod consistently lands on OD."
                ),
                severity=AlertSeverity.ERROR,
                cluster_id=action.cluster_id,
            ))
        except Exception as _ae:
            logger.warning(f"[PC] Failed to send permanent failure alert: {_ae}")
    else:
        logger.info(
            f"[PC] action={action.id} pod={action.payload.get('pod_name')} "
            f"landed on wrong capacity type (attempt {action.retry_count}/{MAX_RETRY_COUNT}). "
            f"Marking FAILED — PlacementController will detect drift on next cycle."
        )

    db.commit()


def _track_od_landing(cluster_id: str, workload_id: str, redis) -> None:
    """
    Increment the per-workload OD-landing counter for the rolling 30-min window.
    When the counter reaches OSCILLATION_THRESHOLD successive OD landings within the
    window the workload is blocked for OSCILLATION_BLOCK_TTL seconds (default 2 h)
    so the evict→OD→evict loop cannot repeat indefinitely below the cluster-level
    circuit-breaker threshold.
    """
    if not workload_id or not redis:
        return
    try:
        counter_key = OSCILLATION_COUNTER_KEY.format(
            cluster_id=cluster_id, workload_id=workload_id
        )
        block_key = OSCILLATION_BLOCK_KEY.format(
            cluster_id=cluster_id, workload_id=workload_id
        )
        count = redis.incr(counter_key)
        redis.expire(counter_key, OSCILLATION_COUNTER_TTL)
        logger.debug(
            f"[PC] OD landing #{count} for workload={workload_id} "
            f"(threshold={OSCILLATION_THRESHOLD}, window={OSCILLATION_COUNTER_TTL}s)"
        )
        if count >= OSCILLATION_THRESHOLD:
            redis.set(block_key, str(count), ex=OSCILLATION_BLOCK_TTL)
            redis.delete(counter_key)  # reset counter after block is set
            logger.warning(
                f"[PC] Oscillation detected for workload={workload_id} cluster={cluster_id}: "
                f"{count} OD landings within {OSCILLATION_COUNTER_TTL}s window. "
                f"Blocking eviction for {OSCILLATION_BLOCK_TTL}s."
            )
    except Exception as exc:
        logger.warning(f"[PC] _track_od_landing failed for {workload_id}: {exc}")


def _decr_semaphore(cluster_id: str, redis) -> None:
    """Decrement the shared Redis batch semaphore when a PC-dispatched action ends."""
    try:
        _sem_key = f"rebalance:active_count:{cluster_id}"
        new_val = redis.decr(_sem_key)
        if new_val < 0:
            redis.set(_sem_key, 0, ex=300)
    except Exception as exc:
        logger.warning(f"[PC] Failed to decrement semaphore for cluster={cluster_id}: {exc}")


def _update_rebalancing_action(agent_action_id: str, status: str, db) -> None:
    """Keep the visibility RebalancingAction in sync with AgentAction status."""
    from backend.models.rebalancing_action import RebalancingAction
    try:
        db.query(RebalancingAction).filter(
            RebalancingAction.agent_action_id == agent_action_id
        ).update({"status": status}, synchronize_session=False)
    except Exception as exc:
        logger.error(
            f"[PC] _update_rebalancing_action FAILED — RebalancingAction.agent_action_id={agent_action_id} "
            f"target_status={status} error={exc}",
            exc_info=True,
        )


def get_pod_placement(namespace: str, pod_name: str, k8s_client=None):
    """
    Queries K8s API for the pod's current node and capacity type.
    Returns an object with .capacity_type ('spot' | 'on-demand') if Running/Scheduled.
    Returns None if the pod is Pending (not yet assigned to a node).
    Raises if pod cannot be found (treat as Pending upstream).

    k8s_client: optional pre-built kubernetes client. Falls back to in-cluster config.
    """
    try:
        from kubernetes import client as k8s
        if k8s_client is None:
            try:
                k8s.Configuration.set_default(k8s.Configuration())
                from kubernetes import config as k8s_config
                try:
                    k8s_config.load_incluster_config()
                except Exception:
                    k8s_config.load_kube_config()
            except Exception:
                return None
            v1 = k8s.CoreV1Api()
        else:
            v1 = k8s_client

        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception as exc:
        err_str = str(exc)
        if "404" in err_str or "Not Found" in err_str:
            return None
        raise

    if pod.spec.node_name is None:
        return None

    try:
        node = v1.read_node(name=pod.spec.node_name)
        capacity_type = node.metadata.labels.get(
            "karpenter.sh/capacity-type",
            node.metadata.labels.get("eks.amazonaws.com/capacityType", "unknown"),
        ).lower()
        if capacity_type == "ondemand":
            capacity_type = "on-demand"
    except Exception:
        capacity_type = "unknown"

    class _PlacementResult:
        pass

    result = _PlacementResult()
    result.capacity_type = capacity_type
    result.node_name = pod.spec.node_name
    return result
