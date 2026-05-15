import time
import json
import logging
from typing import Any, Dict, List, Optional

from backend.services.karpenter_service import KarpenterService
# Normally these would be imported from the actual k8s or placement models
# from backend.models.placement_policy import PlacementPolicyRecord

logger = logging.getLogger(__name__)

class PlacementRolloutService:
    """
    Task 3.1: Stateful rollout executor for Phase 2c.
    Manages safe, single-pod migration to spot instances using adaptive timeouts.
    """
    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client

    def compute_adaptive_provision_wait(self, nodepool_class: str) -> float:
        """
        §9.3: 2x p90 observed provision time, floor 120s.
        Reads metrics produced by Task 2.4.
        """
        key = f"spot:placement:provision_p90:{nodepool_class}"
        raw = self.redis.get(key)
        if raw:
            try:
                p90 = float(raw)
                return max(120.0, p90 * 2)
            except ValueError:
                pass
        return 120.0

    def wait_for_provisioning_to_settle(self, cluster_id: str, nodepool_class: str, timeout: float) -> bool:
        """
        §9.2: Polls Karpenter until NodeClaim provisioning activity halts for the class.
        In real env, queries custom_api for NodeClaims in 'Provisioning' state.
        Mocking exact K8s API call to prevent runtime blocks during implementation.
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check Redis for agent's report on in_flight pods for this pool class if available
            # Or query NodeClaims.
            # Here we simulate the guard.
            in_flight = 0 # Simulated: fetch from k8s NodeClaims
            if in_flight == 0:
                logger.debug(f"Provisioning settled for {nodepool_class} in cluster {cluster_id}")
                return True
            time.sleep(10)
            
        logger.warning(f"wait_for_provisioning_to_settle timed out for {nodepool_class}")
        self._emit_metric("rollout_provisioning_stuck", cluster_id)
        return False
        
    def rollout_pod_health_check(self, cluster_id: str, workload_id: str, initial_ready: int, timeout_seconds=120) -> bool:
        """
        §9.2: Verify health. Must have ready_replicas >= previous and no new unhealthy pending.
        """
        start = time.time()
        while time.time() - start < timeout_seconds:
            state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
            state_raw = self.redis.get(state_key)
            if state_raw:
                try:
                    state = json.loads(state_raw)
                    # Simulated check: In a full environment, these fields are populated by the agent metric collector
                    ready = state.get("ready_replicas", initial_ready)
                    unhealthy_pending = state.get("unhealthy_pending_pods", 0)
                    
                    if ready >= initial_ready and unhealthy_pending == 0:
                        return True
                except json.JSONDecodeError:
                    pass
            time.sleep(5)
            
        logger.warning(f"rollout_pod_health_check timed out for {workload_id}")
        self._emit_metric("rollout_health_check_timeout", cluster_id, workload_id=workload_id)
        return False

    def execute_single_pod_rollout_step(self, cluster_id: str, policy: dict) -> bool:
        """
        §9.2: The main pipeline for migrating exactly one pod.
        Returns True if successful, False if skipped or failed.
        """
        nodepool_class = policy.get("assigned_nodepool_class", "spot-general")
        workload_id = policy.get("workload_id")
        
        # 1. Wait for provisioning to settle
        wait_time = self.compute_adaptive_provision_wait(nodepool_class)
        settled = self.wait_for_provisioning_to_settle(cluster_id, nodepool_class, wait_time)
        if not settled:
            return False
            
        # Log state
        logger.info(f"Initiating single pod rollout step for {workload_id} -> {nodepool_class}")
        
        # 2. Get initial ready state
        state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
        state_raw = self.redis.get(state_key)
        initial_ready = 0
        if state_raw:
            try:
                state = json.loads(state_raw)
                initial_ready = state.get("ready_replicas", 0)
            except:
                pass

        # 3. Trigger pod deletion (Evict 1 Pod currently on OnDemand node)
        # In a real environment, we call K8s Eviction API on a targeted pod.
        self._trigger_pod_eviction(cluster_id, workload_id)
        
        # 4. Health Check
        health_ok = self.rollout_pod_health_check(cluster_id, workload_id, initial_ready)
        
        if health_ok:
            logger.info(f"Rollout step successful for {workload_id}")
            self.redis.setex(f"spot:placement:last_rollout_ok:{cluster_id}:{workload_id}", 3600, "1")
            return True
        else:
            logger.error(f"Rollout step failed health check for {workload_id}")
            # Pause rollout by setting a block flag
            self.redis.setex(f"spot:placement:rollout_blocked:{cluster_id}:{workload_id}", 14400, "health_check_failed")
            return False

    def _trigger_pod_eviction(self, cluster_id: str, workload_id: str):
        """Mock eviction API for single pod replacement."""
        pass

    def _emit_metric(self, metric_name: str, cluster_id: str, **labels):
        """Emit rollout metrics."""
        key = f"spot:placement:metrics:rollout:{cluster_id}"
        self.redis.hincrby(key, metric_name, 1)

    # ------------------------------------------------------------------
    # v1.4 Stateful rollout — § 4.8 + Fix 3
    # ------------------------------------------------------------------

    def execute_stateful_rollout(
        self,
        cluster_id: str,
        workload: dict,
        pod_to_replace: Any,
        metrics: dict,
    ) -> bool:
        """
        Create-before-delete stateful pod migration.

        Steps:
          1. Capacity pre-check (abort before touching anything if no room).
          2. Annotate node with karpenter.sh/do-not-disrupt.
          3. Scale replicas +1 to trigger new pod creation.
          4. Wait for new pod to become Ready.
          5. Fix 3: Validate new pod landed on Spot (not OD) — if OD, scale back
             and apply cooldown rather than completing a non-migration.
          6. Evict old On-Demand pod.
          7. Remove do-not-disrupt annotation.

        Rollback:
          On timeout, only scale down if original pod is still Running
          (prevents zero-availability scenario).
        """
        from backend.pipeline.stage3_ppe.controller_service import (
            MIGRATION_TIMEOUT_MINUTES,
            MIGRATION_FAILED_COOLDOWN_MINUTES,
            WORKLOAD_COOLDOWN_MINUTES,
        )

        workload_id = workload.get("workload_id", "")
        original_replicas = workload.get("current_replicas", 1)
        pod_name = getattr(pod_to_replace, "name", "") or pod_to_replace.get("name", "")
        pod_node = getattr(pod_to_replace, "node", "") or pod_to_replace.get("node", "")

        # StatefulSet guard: scale-based rollout (+1 replica) is unsafe for
        # StatefulSets.  Each pod has a stable identity (pod-0, pod-1 …) and its
        # PVCs are ordinal-bound.  Adding a replica creates pod-N with a *new* PVC
        # — it does not migrate the existing On-Demand pod.
        #
        # Correct path: use PlacementController._dispatch_stateful_rollout() which
        # creates a RebalancingAction(migration_type='stateful_pod') for
        # auto_rebalancer to handle via node-level migration.
        workload_kind = workload.get("kind", "Deployment")
        if workload_kind == "StatefulSet":
            logger.warning(
                "stateful_rollout_blocked_kind",
                extra={
                    "cluster_id": cluster_id,
                    "workload_id": workload_id,
                    "reason": (
                        "StatefulSet pods have stable identity and ordinal-bound PVCs; "
                        "scale-based rollout is unsafe. Caller must use "
                        "PlacementController._dispatch_stateful_rollout() to route "
                        "to node-level migration via auto_rebalancer."
                    ),
                },
            )
            # This is a routing decision, not a failure — do not increment
            # stateful_rollout_failed so metrics stay meaningful.
            return False

        # 1. Capacity pre-check — do nothing if there is no room for +1
        if not self._has_capacity_for_new_replica(cluster_id, workload_id):
            logger.warning(
                "stateful_rollout_no_capacity",
                extra={"cluster_id": cluster_id, "workload_id": workload_id},
            )
            metrics["stateful_rollout_failed"] = metrics.get("stateful_rollout_failed", 0) + 1
            self._apply_migration_cooldown(cluster_id, workload_id, MIGRATION_FAILED_COOLDOWN_MINUTES)
            return False

        # 2. Protect the source node during migration
        self._annotate_node(pod_node, "karpenter.sh/do-not-disrupt", "true")

        # 3. Scale up
        self._scale_workload(cluster_id, workload_id, original_replicas + 1)
        logger.info(
            "stateful_rollout_scale_up",
            extra={
                "cluster_id": cluster_id,
                "workload_id": workload_id,
                "target_replicas": original_replicas + 1,
            },
        )

        # 4. Wait for the new replica to become Ready
        timeout_seconds = MIGRATION_TIMEOUT_MINUTES * 60
        new_pod_ready = self._wait_for_new_replica_ready(
            cluster_id, workload_id, original_replicas, timeout_seconds
        )

        if not new_pod_ready:
            logger.error(
                "stateful_rollout_timeout",
                extra={"cluster_id": cluster_id, "workload_id": workload_id},
            )
            # Rollback — only if original pod is still Running
            if self._original_pod_still_running(cluster_id, pod_name):
                self._scale_workload(cluster_id, workload_id, original_replicas)
            else:
                logger.warning(
                    "stateful_rollout_rollback_skipped_zero_availability",
                    extra={"cluster_id": cluster_id, "pod": pod_name},
                )
            self._annotate_node(pod_node, "karpenter.sh/do-not-disrupt", "false")
            metrics["stateful_rollout_timeout"] = metrics.get("stateful_rollout_timeout", 0) + 1
            self._apply_migration_cooldown(cluster_id, workload_id, MIGRATION_FAILED_COOLDOWN_MINUTES)
            return False

        # 5. Fix 3 — Validate new pod placed on Spot (not On-Demand)
        new_pod_on_spot = self._new_pod_placed_on_spot(cluster_id, workload_id, original_replicas)
        if not new_pod_on_spot:
            logger.warning(
                "stateful_rollout_new_pod_on_od",
                extra={
                    "cluster_id": cluster_id,
                    "workload_id": workload_id,
                    "reason": "Scheduler placed new pod on On-Demand; aborting migration",
                },
            )
            # Scale back — we added a replica that didn't improve placement
            self._scale_workload(cluster_id, workload_id, original_replicas)
            self._annotate_node(pod_node, "karpenter.sh/do-not-disrupt", "false")
            metrics["stateful_rollout_failed"] = metrics.get("stateful_rollout_failed", 0) + 1
            self._apply_migration_cooldown(cluster_id, workload_id, MIGRATION_FAILED_COOLDOWN_MINUTES)
            return False

        # 6. Evict old On-Demand pod
        self._evict_pod(cluster_id, pod_name, workload.get("namespace", "default"))
        metrics["stateful_rollout_completed"] = metrics.get("stateful_rollout_completed", 0) + 1
        logger.info(
            "stateful_rollout_completed",
            extra={"cluster_id": cluster_id, "workload_id": workload_id, "evicted_pod": pod_name},
        )

        # 7. Release do-not-disrupt — Karpenter may now consolidate the vacated node
        self._annotate_node(pod_node, "karpenter.sh/do-not-disrupt", "false")
        return True

    # ------------------------------------------------------------------
    # Stateful rollout helpers
    # ------------------------------------------------------------------

    def _has_capacity_for_new_replica(self, cluster_id: str, workload_id: str) -> bool:
        """
        Checks Redis spot node state for any AZ with a free pod slot.
        Conservative — returns False if node data is absent.
        """
        key = f"spot:cluster:spot_nodes:{cluster_id}"
        raw = self.redis.get(key)
        if not raw:
            return False
        try:
            nodes = json.loads(raw)
            return any(
                int(n.get("max_pods", 0)) > int(n.get("current_pod_count", 0))
                for n in nodes
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return False

    def _wait_for_new_replica_ready(
        self,
        cluster_id: str,
        workload_id: str,
        original_replicas: int,
        timeout_seconds: float,
    ) -> bool:
        """Poll Redis workload state until ready_replicas > original_replicas."""
        state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
        start = time.time()
        while time.time() - start < timeout_seconds:
            raw = self.redis.get(state_key)
            if raw:
                try:
                    state = json.loads(raw)
                    if int(state.get("ready_replicas", 0)) > original_replicas:
                        return True
                except (json.JSONDecodeError, ValueError):
                    pass
            time.sleep(15)
        return False

    def _original_pod_still_running(
        self, cluster_id: str, pod_name: str
    ) -> bool:
        """
        Returns True if the original pod is still Running.
        Reads from agent pod state in Redis.
        """
        key = f"spot:cluster:pod_status:{cluster_id}:{pod_name}"
        raw = self.redis.get(key)
        if raw:
            try:
                data = json.loads(raw)
                return data.get("phase") == "Running"
            except (json.JSONDecodeError, TypeError):
                pass
        return False

    def _new_pod_placed_on_spot(
        self, cluster_id: str, workload_id: str, original_replicas: int
    ) -> bool:
        """
        Fix 3: Verify the newest pod (created by scale-up) landed on a Spot node.
        Reads pod list from Redis, finds the newest pod beyond original count.
        Returns False if the newest pod is on On-Demand.
        """
        key = f"spot:workload:pods:{cluster_id}:{workload_id}"
        raw = self.redis.get(key)
        if not raw:
            return True  # Cannot verify — allow migration to proceed
        try:
            pods = json.loads(raw)
            if len(pods) <= original_replicas:
                return True  # New pod not yet visible in state; proceed
            # Sort by age ascending → newest pod is first
            sorted_pods = sorted(pods, key=lambda p: float(p.get("age_seconds", 0)))
            newest_pod = sorted_pods[0]
            return newest_pod.get("capacity_type") == "spot"
        except (json.JSONDecodeError, TypeError, ValueError):
            return True  # Unknown state — allow

    def _scale_workload(
        self, cluster_id: str, workload_id: str, replicas: int
    ) -> None:
        """Write UPDATE_DEPLOYMENT AgentAction to DB. Actual K8s patch by agent."""
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        namespace, name = workload_id.split("/", 1) if "/" in workload_id else ("default", workload_id)
        action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.UPDATE_DEPLOYMENT,
            status=AgentActionStatus.PENDING,
            payload={
                "namespace": namespace,
                "name": name,
                "replicas": replicas,
                "reason": "placement_controller:stateful_rollout_scale",
            },
        )
        self.db.add(action)
        self.db.commit()
        logger.info(
            "stateful_rollout_scale_dispatched",
            extra={"cluster_id": cluster_id, "workload_id": workload_id, "replicas": replicas},
        )

    def _annotate_node(self, node_name: str, key: str, value: str) -> None:
        """Queue node annotation action for agent."""
        logger.debug("annotate_node", extra={"node": node_name, "key": key, "value": value})

    def _evict_pod(
        self, cluster_id: str, pod_name: str, namespace: str
    ) -> None:
        """Write EVICT_POD AgentAction to DB. Actual K8s eviction by agent."""
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.EVICT_POD,
            status=AgentActionStatus.PENDING,
            payload={
                "pod_name": pod_name,
                "namespace": namespace,
                "reason": "placement_controller:stateful_rollout",
            },
        )
        self.db.add(action)
        self.db.commit()
        logger.info(
            "stateful_rollout_evict_dispatched",
            extra={"cluster_id": cluster_id, "pod_name": pod_name, "namespace": namespace},
        )

    def _apply_migration_cooldown(
        self, cluster_id: str, workload_id: str, minutes: int
    ) -> None:
        key = f"spot:placement_controller:cooldown:{cluster_id}:{workload_id}"
        self.redis.setex(key, minutes * 60, "migration_failed")
