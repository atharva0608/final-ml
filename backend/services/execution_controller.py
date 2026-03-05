"""
Execution Controller — Safe Node Replacement Pipeline
======================================================
⚠️  DEPRECATED — THIS CLASS IS DEAD CODE. DO NOT USE IN NEW FEATURES.

Why it's deprecated:
  The auto-rebalancer (backend/workers/tasks/auto_rebalancer.py) is the real,
  working execution path. It creates AgentAction records in PostgreSQL which the
  K8s DaemonSet agent picks up via WebSocket or HTTP polling and executes directly.

  ExecutionController was an alternative design that never got wired to real AWS/K8s
  calls. Every adapter method here returns a hardcoded True stub — it has NEVER
  performed an actual node drain, EC2 termination, or capacity check in production.

Real execution path (use these instead):
  1. auto_rebalancer.py → create_pool_switch_actions() → 3 AgentAction records
  2. agent_routes.py → WebSocket push / HTTP poll → agent/actuator.py
  3. actuator.py → cordon_node(), drain_node(), patch_karpenter_nodepool()
  4. agent_routes.py POST /actions/{id}/result → record result + SSE event

This file is kept only because test_integration_hardening.py mocks it.
Do not add new functionality here. This will be removed in a future cleanup.

Implements problems.md §7:
  1. Dry-run capacity validation
  2. Provision substitute node
  3. Wait for substitute to be Ready
  4. Drain original node (cordon + evict pods)
  5. Verify workload health
  6. Terminate original node

Rollback on any failure → increments rollback counter → circuit breaker.
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


class ExecutionController:  # DEPRECATED — see module docstring for real path
    """
    Orchestrates zero-downtime spot node replacement.
    Uses injected adapters for K8s and AWS operations.
    """

    def __init__(
        self,
        k8s_client=None,
        aws_client=None,
        redis_client=None,
        circuit_breaker=None,
        substitute_manager=None,
        guardrail_engine_fn=None,
    ):
        self.k8s = k8s_client
        self.aws = aws_client
        self.redis = redis_client
        self.circuit_breaker = circuit_breaker
        self.substitute_manager = substitute_manager
        self.check_guardrails = guardrail_engine_fn  # callable or None

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
        """Validate capacity availability via AWS EC2 dry-run."""
        # Production: call boto3 EC2 run_instances(DryRun=True)
        logger.info(f"[ExecCtrl] Dry-run capacity check: {instance_type} in {az}/{region}")
        return True, f"Capacity available for {instance_type} in {az}"

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
        """Poll until substitute node is Kubernetes-Ready."""
        logger.info(f"[ExecCtrl] Waiting for substitute {substitute_id} to be Ready")
        # Production: poll k8s CoreV1Api node status
        return True, f"Substitute {substitute_id} is Ready"

    def _drain_node(self, cluster_id: str, node_id: str) -> Tuple[bool, str]:
        """Cordon + drain (evict all pods) from the source node."""
        logger.info(f"[ExecCtrl] Draining node {node_id} in cluster {cluster_id}")
        # Production: kubectl cordon + kubectl drain --ignore-daemonsets
        return True, f"Node {node_id} cordoned and drained"

    def _verify_workload_health(self, cluster_id: str) -> Tuple[bool, str]:
        """Check that all pods are running after drain."""
        logger.info(f"[ExecCtrl] Verifying workload health for cluster {cluster_id}")
        # Production: query pod_metrics + pending pod count
        return True, "All pods running, workload healthy"

    def _rollback_drain(self, cluster_id: str, node_id: str):
        """Un-cordon the drained node to restore capacity."""
        logger.warning(f"[ExecCtrl] Rolling back drain on {node_id}")
        # Production: kubectl uncordon

    def _terminate_node(self, cluster_id: str, node_id: str) -> Tuple[bool, str]:
        """Terminate the original EC2 instance."""
        logger.info(f"[ExecCtrl] Terminating original node {node_id}")
        # Production: boto3 ec2.terminate_instances([node_id])
        return True, f"Node {node_id} terminated"
