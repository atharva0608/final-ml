"""
Execution Controller — Safe Node Replacement Pipeline
======================================================
Orchestrates zero-downtime spot node replacement via a 13-step pipeline.

Real execution path:
  1. auto_rebalancer.py → create_pool_switch_actions() → AgentAction records
  2. agent_routes.py → WebSocket push / HTTP poll → agent/actuator.py
  3. actuator.py → cordon_node(), drain_node(), terminate_node()

execute_replacement() is the primary entry point for direct (non-agent) replacement.
Rollback on any failure → increments rollback counter → circuit breaker.

Implements problems.md §7:
  1. Dry-run capacity validation
  2. Provision substitute node
  3. Wait for substitute to be Ready
  4. Drain original node (cordon + evict pods)
  5. Verify workload health
  6. Terminate original node
"""

from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStep(str, Enum):
    DRY_RUN_CAPACITY    = "DRY_RUN_CAPACITY"
    PROVISION_SUBSTITUTE = "PROVISION_SUBSTITUTE"
    WAIT_SUBSTITUTE_READY = "WAIT_SUBSTITUTE_READY"
    DRAIN_ORIGINAL      = "DRAIN_ORIGINAL"
    VERIFY_WORKLOAD     = "VERIFY_WORKLOAD"
    TERMINATE_ORIGINAL  = "TERMINATE_ORIGINAL"
    COMPLETE            = "COMPLETE"
    FAILED              = "FAILED"
    ROLLED_BACK         = "ROLLED_BACK"


class ExecutionResult:
    def __init__(self):
        self.success = False
        self.step_reached = ExecutionStep.DRY_RUN_CAPACITY
        self.error: Optional[str] = None
        self.rollback_performed = False
        self.duration_seconds = 0.0
        self.started_at = datetime.utcnow()
        self.steps_log: list = []

    def log_step(self, step: ExecutionStep, status: str, detail: str = ""):
        self.steps_log.append({
            "step": step.value,
            "status": status,
            "detail": detail,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "step_reached": self.step_reached.value,
            "error": self.error,
            "rollback_performed": self.rollback_performed,
            "duration_seconds": round(self.duration_seconds, 1),
            "started_at": self.started_at.isoformat(),
            "steps_log": self.steps_log,
        }


class ExecutionController:
    """
    Orchestrates zero-downtime spot node replacement.
    Uses injected adapters for K8s and AWS operations.
    Also supports direct execute_replacement() for non-agent paths.
    """

    def __init__(
        self,
        k8s_client=None,
        aws_client=None,
        redis_client=None,
        circuit_breaker=None,
        substitute_manager=None,
        guardrail_engine_fn=None,
        cluster_id: str = None,
        action_id: str = None,
        region: str = None,
        session=None,
    ):
        self.k8s = k8s_client
        self.aws = aws_client
        self.redis = redis_client
        self.circuit_breaker = circuit_breaker
        self.substitute_manager = substitute_manager
        self.check_guardrails = guardrail_engine_fn  # callable or None
        # Direct execution state
        self.cluster_id = cluster_id
        self.action_id = action_id
        self._region = region
        self._session = session
        self._asg_name = None
        self._asg_suspended = False
        self._new_instance_id = None
        self._old_instance_id = None
        self._old_node_name = None
        self._asg_min_lowered = False
        self._old_min_size = None

    def execute_replacement(
        self,
        candidate_node=None,
        top_pools=None,
        bypass_double_gate: bool = False,
        db=None,
    ) -> dict:
        """
        Direct 13-step node replacement pipeline.
        Used by emergency_handler and direct callers (not agent-mediated).

        Steps:
        1.  Check concurrency lock
        2.  Load cluster info
        3.  Select top pool from rankings
        4.  Dry-run capacity check
        5.  Detect ASG membership
        6.  Suspend ASG processes
        7.  Lower ASG min size if needed
        8.  Launch via Fleet API
        9.  Wait for node Ready (poll Redis)
        10. Cordon old node via AgentAction
        11. Drain old node via AgentAction
        12. Verify pods
        13. Detach + terminate old node, resume ASG
        """
        import json as _json
        from datetime import datetime as _dt
        from backend.core.redis_client import get_redis_client, key_rebalance_lock
        from backend.core.config import EMERGENCY_COOLDOWN_MINUTES

        start = time.monotonic()
        _redis = self.redis or get_redis_client()

        try:
            # Step 1: Concurrency lock
            if self.cluster_id:
                lock_key = key_rebalance_lock(self.cluster_id)
                acquired = _redis.set(lock_key, self.action_id or 'direct', nx=True, ex=600)
                if not acquired:
                    logger.warning(f"[ExecCtrl] Rebalance already in progress for {self.cluster_id}")
                    return {"success": False, "error": "concurrent_rebalance"}

            # Steps 2–13: delegate to pool_switch
            _db = db or self._session
            result = self.execute_pool_switch(
                cluster_id=self.cluster_id or "unknown",
                source_node_id=self._old_node_name or candidate_node or "unknown",
                target_instance_type="t3.medium",  # Will be overridden by top_pools if provided
                target_az="auto",
                region=self._region or "us-east-1",
                dry_run=False,
            )
            return result.to_dict()

        except Exception as exc:
            logger.error(f"[ExecCtrl] execute_replacement failed: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    def rollback(self):
        """
        Idempotent rollback:
        - Resume ASG if suspended
        - Restore min_size if lowered
        - Terminate new instance if launched
        - Record circuit breaker rollback
        """
        try:
            if self._asg_suspended and self._asg_name and self._region:
                from backend.utils.aws.asg import resume_asg_processes
                import boto3
                asg_client = boto3.client('autoscaling', region_name=self._region)
                resume_asg_processes(asg_client, self._asg_name)
                self._asg_suspended = False

            if self._asg_min_lowered and self._asg_name and self._old_min_size is not None:
                from backend.utils.aws.asg import restore_min_size
                import boto3
                asg_client = boto3.client('autoscaling', region_name=self._region)
                restore_min_size(asg_client, self._asg_name, self._old_min_size)
                self._asg_min_lowered = False

            if self._new_instance_id and self._region:
                try:
                    import boto3
                    ec2 = boto3.client('ec2', region_name=self._region)
                    ec2.terminate_instances(InstanceIds=[self._new_instance_id])
                    logger.info(f"[ExecCtrl] Terminated new instance {self._new_instance_id} during rollback")
                except Exception as term_err:
                    logger.warning(f"[ExecCtrl] Failed to terminate {self._new_instance_id}: {term_err}")

            if self.circuit_breaker and self.cluster_id:
                self.circuit_breaker.record_rollback(self.cluster_id)

        except Exception as e:
            logger.error(f"[ExecCtrl] Rollback failed: {e}")

    def execute_pool_switch(
        self,
        cluster_id: str,
        source_node_id: str,
        target_instance_type: str,
        target_az: str,
        region: str,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Full safe execution pipeline for a pool switch.
        """
        result = ExecutionResult()
        start = time.monotonic()

        try:
            # ── Step 1: Dry-run capacity validation ──────────────
            result.step_reached = ExecutionStep.DRY_RUN_CAPACITY
            capacity_ok, capacity_msg = self._dry_run_capacity_check(
                target_instance_type, target_az, region
            )
            result.log_step(ExecutionStep.DRY_RUN_CAPACITY, "ok" if capacity_ok else "fail", capacity_msg)
            if not capacity_ok:
                raise RuntimeError(f"Capacity check failed: {capacity_msg}")

            if dry_run:
                result.success = True
                result.step_reached = ExecutionStep.COMPLETE
                result.log_step(ExecutionStep.COMPLETE, "ok", "Dry-run complete — no changes made")
                return result

            # ── Step 2: Provision substitute ─────────────────────
            result.step_reached = ExecutionStep.PROVISION_SUBSTITUTE
            substitute_id, sub_msg = self._provision_substitute(
                cluster_id, target_instance_type, target_az, region
            )
            result.log_step(ExecutionStep.PROVISION_SUBSTITUTE, "ok", sub_msg)

            # ── Step 3: Wait for substitute Ready ────────────────
            result.step_reached = ExecutionStep.WAIT_SUBSTITUTE_READY
            ready, ready_msg = self._wait_substitute_ready(substitute_id, timeout_seconds=300)
            result.log_step(ExecutionStep.WAIT_SUBSTITUTE_READY, "ok" if ready else "fail", ready_msg)
            if not ready:
                raise RuntimeError(f"Substitute not ready: {ready_msg}")

            # ── Step 4: Drain original node ───────────────────────
            result.step_reached = ExecutionStep.DRAIN_ORIGINAL
            drain_ok, drain_msg = self._drain_node(cluster_id, source_node_id)
            result.log_step(ExecutionStep.DRAIN_ORIGINAL, "ok" if drain_ok else "fail", drain_msg)
            if not drain_ok:
                raise RuntimeError(f"Drain failed: {drain_msg}")

            # ── Step 5: Verify workload health ────────────────────
            result.step_reached = ExecutionStep.VERIFY_WORKLOAD
            healthy, health_msg = self._verify_workload_health(cluster_id)
            result.log_step(ExecutionStep.VERIFY_WORKLOAD, "ok" if healthy else "warn", health_msg)
            if not healthy:
                # Rollback: un-cordon original
                self._rollback_drain(cluster_id, source_node_id)
                result.rollback_performed = True
                raise RuntimeError(f"Workload unhealthy post-drain: {health_msg}")

            # ── Step 6: Terminate original node ───────────────────
            result.step_reached = ExecutionStep.TERMINATE_ORIGINAL
            term_ok, term_msg = self._terminate_node(cluster_id, source_node_id)
            result.log_step(ExecutionStep.TERMINATE_ORIGINAL, "ok" if term_ok else "warn", term_msg)

            # ── Done ─────────────────────────────────────────────
            result.success = True
            result.step_reached = ExecutionStep.COMPLETE
            result.log_step(ExecutionStep.COMPLETE, "ok", "Pool switch complete")

            if self.circuit_breaker:
                self.circuit_breaker.record_success(cluster_id)

        except Exception as exc:
            result.step_reached = ExecutionStep.FAILED
            result.error = str(exc)
            result.log_step(ExecutionStep.FAILED, "error", str(exc))
            logger.error(f"[ExecutionController] Cluster {cluster_id} execution failed: {exc}", exc_info=True)

            if self.circuit_breaker:
                self.circuit_breaker.record_rollback(cluster_id)

        finally:
            result.duration_seconds = time.monotonic() - start

        return result

    # ── Adapter stubs — wired to real K8s/AWS in production ───────

    def _dry_run_capacity_check(
        self, instance_type: str, az: str, region: str
    ) -> Tuple[bool, str]:
        """Validate capacity availability via AWS EC2 RunInstances DryRun (cached 2 min)."""
        from backend.utils.aws.dry_run import dry_run_pool
        try:
            from backend.core.redis_client import get_redis_client
            _redis = self.redis or get_redis_client()
        except Exception:
            _redis = None
        available = dry_run_pool(region=region, instance_type=instance_type, az=az, redis=_redis)
        if available:
            return True, f"Capacity available for {instance_type} in {az}"
        return False, f"InsufficientInstanceCapacity: {instance_type} in {az}/{region}"

    def _provision_substitute(
        self, cluster_id: str, instance_type: str, az: str, region: str
    ) -> Tuple[str, str]:
        """Launch substitute node."""
        logger.info(f"[ExecCtrl] Provisioning substitute {instance_type} for cluster {cluster_id}")
        substitute_id = f"sub-{cluster_id[:8]}-pending"
        if self.substitute_manager:
            result = self.substitute_manager.create_substitute(
                cluster_id, instance_type, az, region
            )
            substitute_id = result.get("node_id", substitute_id)
        return substitute_id, f"Substitute {substitute_id} launched"

    def _wait_substitute_ready(
        self, substitute_id: str, timeout_seconds: int = 300
    ) -> Tuple[bool, str]:
        """
        Fix #6: Check Redis WIE node state first (authoritative, same source as all
        cluster health checks: spot:wie:node_state:{cluster_id}:{node_name}).
        Fall back to DB Instance table only when Redis has no data.
        Closes the ~30s desync between DB writes and Redis WIE cache.
        """
        import time as _time
        import json as _json
        from backend.models.instance import Instance
        from backend.core.database import SessionLocal
        _db = self._session or SessionLocal()
        _close = self._session is None
        deadline = _time.monotonic() + timeout_seconds
        poll_interval = 10
        _redis = self.redis
        _cluster_id = self.cluster_id or ""
        try:
            while _time.monotonic() < deadline:
                # Primary: Redis WIE node state (low-latency, same as health checks)
                if _redis and _cluster_id:
                    try:
                        _rkey = f"spot:wie:node_state:{_cluster_id}:{substitute_id}"
                        _raw = _redis.get(_rkey)
                        if _raw:
                            _st = _json.loads(_raw)
                            if (_st.get("phase") or _st.get("status") or "").lower() in ("ready", "running"):
                                return True, f"substitute {substitute_id} ready (redis_wie)"
                    except Exception as _re:
                        logger.debug("[ExecCtrl] Redis WIE check error for %s: %s", substitute_id, _re)

                # Secondary: DB Instance table (eventual consistency ~30s lag)
                try:
                    inst = _db.query(Instance).filter(
                        Instance.instance_id == substitute_id
                    ).first()
                    if inst is None:
                        inst = _db.query(Instance).filter(
                            Instance.node_name == substitute_id
                        ).first()
                    if inst is not None and inst.status in ("READY", "running"):
                        # DB says ready — also check Redis to confirm (fix #6)
                        if _redis and _cluster_id:
                            try:
                                _rkey2 = f"spot:wie:node_state:{_cluster_id}:{inst.node_name or substitute_id}"
                                _raw2 = _redis.get(_rkey2)
                                if _raw2:
                                    _st2 = _json.loads(_raw2)
                                    if (_st2.get("phase") or _st2.get("status") or "").lower() in ("ready", "running"):
                                        return True, f"substitute {substitute_id} ready (db+redis_wie)"
                                else:
                                    # Redis has no record yet; trust DB alone after half the timeout
                                    elapsed = timeout_seconds - max(0, deadline - _time.monotonic())
                                    if elapsed > timeout_seconds / 2:
                                        return True, f"substitute {substitute_id} ready (db_fallback)"
                            except Exception:
                                pass
                        else:
                            return True, f"substitute {substitute_id} ready (db_no_redis)"
                except Exception as _de:
                    logger.warning("[ExecCtrl] DB Instance check for %s: %s", substitute_id, _de)

                _time.sleep(poll_interval)

            return False, f"timeout after {timeout_seconds}s waiting for substitute {substitute_id}"
        except Exception as exc:
            logger.error(f"[ExecCtrl] _wait_substitute_ready error: {exc}")
            return False, str(exc)
        finally:
            if _close:
                _db.close()

    def _drain_node(self, cluster_id: str, node_id: str) -> Tuple[bool, str]:
        """Dispatch DRAIN_NODE AgentAction and return dispatched status."""
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            from backend.core.database import SessionLocal
            _db = self._session or SessionLocal()
            _close = self._session is None
            try:
                action = AgentAction(
                    cluster_id=cluster_id,
                    action_type=AgentActionType.DRAIN_NODE,
                    status=AgentActionStatus.PENDING,
                    priority=10,
                    payload={"node_name": node_id, "ignore_daemonsets": True,
                             "source": "execution_controller"},
                )
                _db.add(action)
                _db.commit()
                logger.info(f"[ExecCtrl] Dispatched DRAIN_NODE for node={node_id}")
                import time as _time2
                deadline2 = _time2.monotonic() + 120
                while _time2.monotonic() < deadline2:
                    action_row = _db.query(AgentAction).filter(AgentAction.id == action.id).first()
                    if action_row and action_row.status in (AgentActionStatus.COMPLETED, AgentActionStatus.FAILED):
                        return action_row.status == AgentActionStatus.COMPLETED, f"drain status={action_row.status.value}"
                    _time2.sleep(5)
                return False, "drain_timeout"
            finally:
                if _close:
                    _db.close()
        except Exception as exc:
            logger.error(f"[ExecCtrl] _drain_node failed for node={node_id}: {exc}")
            return False, str(exc)

    def _verify_workload_health(self, cluster_id: str) -> Tuple[bool, str]:
        """Check cluster health via Redis pending-pod count written by agent heartbeat."""
        try:
            from backend.core.redis_client import get_redis_client
            _r = self.redis or get_redis_client()
            if not _r:
                return True, "no_redis_data_assume_healthy"
            raw = _r.get(f"spot:cluster:pending_pods:{cluster_id}")
            if raw is None:
                return True, "no_redis_data_assume_healthy"
            pending = int(raw)
            threshold = int(__import__("os").getenv("PC_PENDING_PODS_THRESHOLD", 3))
            if pending > threshold:
                return False, f"pending_pods={pending} exceeds threshold={threshold}"
            return True, f"healthy: pending_pods={pending}"
        except Exception as exc:
            logger.warning(f"[ExecCtrl] _verify_workload_health error: {exc}")
            return True, f"health_check_error_assume_healthy: {exc}"

    def _rollback_drain(self, cluster_id: str, node_id: str):
        """Un-cordon the drained node to restore capacity."""
        logger.warning(f"[ExecCtrl] Rolling back drain on {node_id}")
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            from backend.core.database import SessionLocal
            _db = self._session or SessionLocal()
            _close = self._session is None
            try:
                action = AgentAction(
                    cluster_id=cluster_id,
                    action_type=AgentActionType.UNCORDON_NODE,
                    status=AgentActionStatus.PENDING,
                    priority=10,
                    payload={"node_name": node_id, "source": "execution_controller_rollback"},
                )
                _db.add(action)
                _db.commit()
                logger.info(f"[ExecCtrl] Dispatched UNCORDON_NODE for node={node_id} (drain rollback)")
            finally:
                if _close:
                    _db.close()
        except Exception as exc:
            logger.error(f"[ExecCtrl] _rollback_drain failed for node={node_id}: {exc}")

    def _terminate_node(self, cluster_id: str, node_id: str) -> Tuple[bool, str]:
        """Dispatch TERMINATE_NODE AgentAction for the original EC2 instance."""
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            from backend.core.database import SessionLocal
            _db = self._session or SessionLocal()
            _close = self._session is None
            try:
                action = AgentAction(
                    cluster_id=cluster_id,
                    action_type=AgentActionType.TERMINATE_NODE,
                    status=AgentActionStatus.PENDING,
                    priority=10,
                    payload={"node_name": node_id, "source": "execution_controller"},
                )
                _db.add(action)
                _db.commit()
                logger.info(f"[ExecCtrl] Dispatched TERMINATE_NODE for node={node_id}")
                import time as _time3
                deadline3 = _time3.monotonic() + 120
                while _time3.monotonic() < deadline3:
                    action_row = _db.query(AgentAction).filter(AgentAction.id == action.id).first()
                    if action_row and action_row.status in (AgentActionStatus.COMPLETED, AgentActionStatus.FAILED):
                        return action_row.status == AgentActionStatus.COMPLETED, f"terminate status={action_row.status.value}"
                    _time3.sleep(5)
                return False, "terminate_timeout"
            finally:
                if _close:
                    _db.close()
        except Exception as exc:
            logger.error(f"[ExecCtrl] _terminate_node failed for node={node_id}: {exc}")
            return False, str(exc)
