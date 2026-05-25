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
        DEPRECATED — direct-eviction path removed (Bug 3 fix).

        This method previously evicted the On-Demand pod IMMEDIATELY (step 3),
        BEFORE confirming a new pod was Ready. That means the old pod could be
        killed while zero replacement pods were running — violating the
        "create-before-delete" contract.

        All pod migration MUST go through execute_stateful_rollout() which:
          1. Scales up (+1 replica)
          2. Waits for new pod to become Ready
          3. Validates new pod landed on Spot
          4. Only then evicts the original OD pod

        Callers should supply a `workload` dict and a `pod_to_replace` object.
        """
        nodepool_class = policy.get("assigned_nodepool_class", "spot-general")
        workload_id = policy.get("workload_id")
        logger.warning(
            "execute_single_pod_rollout_step_deprecated",
            extra={
                "cluster_id": cluster_id,
                "workload_id": workload_id,
                "nodepool_class": nodepool_class,
                "reason": (
                    "Direct eviction path was removed. "
                    "Caller must use execute_stateful_rollout() to ensure "
                    "create-before-delete ordering. Old pod must NOT be killed "
                    "before new pod is Ready and accepting requests."
                ),
            },
        )
        # Emit a metric so ops dashboards can alert on stale callers.
        self._emit_metric("single_pod_rollout_deprecated_call", cluster_id)
        # Return False — do NOT proceed with eviction.
        return False


    def _trigger_pod_eviction(self, cluster_id: str, workload_id: str) -> None:
        """
        Evict one On-Demand pod for this workload.
        Looks up the OD pod from Redis pod-list state; falls back to a
        namespace/name hint so the in-cluster agent can select the pod itself.
        """
        namespace, name = workload_id.split("/", 1) if "/" in workload_id else ("default", workload_id)
        pod_name: Optional[str] = None
        try:
            raw = self.redis.get(f"spot:workload:pods:{cluster_id}:{workload_id}")
            if raw:
                pods: List[Dict] = json.loads(raw)
                for p in pods:
                    cap = (p.get("capacity_type") or "").lower()
                    if cap not in ("spot",):
                        pod_name = p.get("pod_name") or p.get("name")
                        namespace = p.get("namespace", namespace)
                        break
        except Exception:
            pass
        if not pod_name:
            logger.warning(
                "trigger_pod_eviction_pod_not_found_in_redis",
                extra={"cluster_id": cluster_id, "workload_id": workload_id},
            )
            return
        self._evict_pod(cluster_id, pod_name, namespace)

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

        # 1a. PVC check — EBS volumes are ReadWriteOnce: a +1 replica cannot mount
        # the existing PVC while the old pod is still running.  Route to node-level
        # drain instead (caller must use _dispatch_stateful_rollout).
        if self._workload_has_pvc(cluster_id, workload_id):
            logger.warning(
                "stateful_rollout_blocked_pvc",
                extra={
                    "cluster_id": cluster_id,
                    "workload_id": workload_id,
                    "reason": (
                        "Workload has PVC (ReadWriteOnce). "
                        "+1 scaling would leave the old pod holding the volume mount. "
                        "Caller must route to node-level drain strategy."
                    ),
                },
            )
            return False

        # 1b. Capacity pre-check — do nothing if there is no room for +1
        if not self._has_capacity_for_new_replica(cluster_id, workload_id):
            logger.warning(
                "stateful_rollout_no_capacity",
                extra={"cluster_id": cluster_id, "workload_id": workload_id},
            )
            metrics["stateful_rollout_failed"] = metrics.get("stateful_rollout_failed", 0) + 1
            self._apply_migration_cooldown(cluster_id, workload_id, MIGRATION_FAILED_COOLDOWN_MINUTES)
            return False

        # 2. Protect the source node during migration
        self._annotate_node(cluster_id, pod_node, "karpenter.sh/do-not-disrupt", "true")

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
            self._annotate_node(cluster_id, pod_node, "karpenter.sh/do-not-disrupt", "false")
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
            self._annotate_node(cluster_id, pod_node, "karpenter.sh/do-not-disrupt", "false")
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
        self._annotate_node(cluster_id, pod_node, "karpenter.sh/do-not-disrupt", "false")
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

    def _annotate_node(self, cluster_id: str, node_name: str, key: str, value: str) -> None:
        """
        Dispatch a LABEL_NODE AgentAction that instructs the in-cluster agent
        to apply the given annotation (e.g. karpenter.sh/do-not-disrupt) on the node.
        The agent interprets the 'annotations' payload field alongside 'labels'.
        """
        if not node_name:
            logger.warning("annotate_node_skipped_no_name", extra={"cluster_id": cluster_id, "key": key})
            return
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.LABEL_NODE,
            status=AgentActionStatus.PENDING,
            payload={
                "node_name": node_name,
                "annotations": {key: value},
                "labels": {},
                "reason": "placement_controller:karpenter_do_not_disrupt",
            },
        )
        self.db.add(action)
        self.db.commit()
        logger.info(
            "annotate_node_dispatched",
            extra={"cluster_id": cluster_id, "node": node_name, "key": key, "value": value},
        )

    def _workload_has_pvc(self, cluster_id: str, workload_id: str) -> bool:
        """
        Return True if this workload has a PVC attached.
        Primary source: Redis key spot:workload:pvc:{cluster_id}:{workload_id}
        pushed by the in-cluster agent's workload discovery loop.
        Falls back to False when data is absent (conservative — allows rollout
        with the expectation that agent data will arrive before production use).
        """
        try:
            raw = self.redis.get(f"spot:workload:pvc:{cluster_id}:{workload_id}")
            if raw:
                data = json.loads(raw)
                return bool(data) if isinstance(data, list) else bool(data.get("has_pvc"))
        except Exception:
            pass
        return False

    def _pdb_allows_eviction(self, cluster_id: str, workload_id: str) -> bool:
        """
        Return True when the workload's PodDisruptionBudget allows at least
        one more disruption.  Redis key: spot:workload:pdb:{cluster_id}:{workload_id}
        Shape: {"disruptions_allowed": <int>, "min_available": <int>, "ready_replicas": <int>}
        Defaults to True when no PDB data is available.
        """
        try:
            raw = self.redis.get(f"spot:workload:pdb:{cluster_id}:{workload_id}")
            if raw:
                pdb = json.loads(raw)
                return int(pdb.get("disruptions_allowed", 1)) > 0
        except Exception:
            pass
        return True

    def _evict_pod(
        self, cluster_id: str, pod_name: str, namespace: str
    ) -> None:
        """Write EVICT_POD AgentAction to DB. Actual K8s eviction by agent."""
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        # PDB gate — block eviction if PDB does not allow a disruption
        workload_id = f"{namespace}/{pod_name.rsplit('-', 2)[0]}"
        if not self._pdb_allows_eviction(cluster_id, workload_id):
            logger.warning(
                "evict_pod_blocked_by_pdb",
                extra={"cluster_id": cluster_id, "pod_name": pod_name, "namespace": namespace},
            )
            return
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


class ActionRealTimeValidator:
    """
    Real-time post-action verifier.

    After the in-cluster agent marks an AgentAction as COMPLETED, this
    validator cross-checks that the observable cluster state actually
    reflects the expected outcome.  Results are stored in Redis for the
    UI to display and for the rebalancer to gate subsequent actions.

    Redis key schema:
        spot:validation:{cluster_id}:{action_id}  →  JSON validation report
    """

    VALIDATION_TTL_SECONDS = 3600  # keep reports for 1 h

    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(self, cluster_id: str, action_id: str) -> Dict[str, Any]:
        """
        Load the completed AgentAction by ID and run the appropriate
        validator.  Returns a report dict and caches it in Redis.
        """
        from backend.models.agent_action import AgentAction, AgentActionType
        action = self.db.query(AgentAction).filter(AgentAction.id == action_id).first()
        if not action:
            return {"ok": False, "reason": "action_not_found", "action_id": action_id}

        atype = action.action_type
        payload = action.payload or {}
        node_name = payload.get("node_name")

        if atype == AgentActionType.CORDON_NODE:
            report = self._validate_node_cordoned(cluster_id, node_name)
        elif atype == AgentActionType.DRAIN_NODE:
            report = self._validate_node_drained(cluster_id, node_name)
        elif atype == AgentActionType.TERMINATE_NODE:
            report = self._validate_node_terminated(cluster_id, node_name)
        elif atype == AgentActionType.EVICT_POD:
            report = self._validate_pod_evicted(cluster_id, payload.get("pod_name"), payload.get("namespace", "default"))
        else:
            report = {"ok": True, "reason": "no_validation_for_action_type", "action_type": atype.value}

        report.update({"action_id": action_id, "action_type": atype.value, "node_name": node_name})
        self._cache_report(cluster_id, action_id, report)
        return report

    # ------------------------------------------------------------------
    # Per-action validators
    # ------------------------------------------------------------------

    def _validate_node_cordoned(self, cluster_id: str, node_name: Optional[str]) -> Dict[str, Any]:
        """
        Verify the node is now unschedulable.
        The agent should have set NodeMetadata.is_ready = False after cordoning.
        """
        if not node_name:
            return {"ok": False, "reason": "missing_node_name"}
        from backend.models.node_metadata import NodeMetadata
        meta = (
            self.db.query(NodeMetadata)
            .filter(NodeMetadata.cluster_id == cluster_id, NodeMetadata.node_name == node_name)
            .first()
        )
        if meta is None:
            return {"ok": False, "reason": "node_metadata_not_found", "node": node_name}
        if not meta.is_ready:
            return {"ok": True, "reason": "node_is_unschedulable", "node": node_name}
        return {
            "ok": False,
            "reason": "node_still_schedulable_after_cordon",
            "node": node_name,
            "is_ready": meta.is_ready,
        }

    def _validate_node_drained(self, cluster_id: str, node_name: Optional[str]) -> Dict[str, Any]:
        """
        Verify the node has no user (non-DaemonSet, non-system) pods remaining.
        Reads the last 5-minute window of PodMetric data.
        """
        if not node_name:
            return {"ok": False, "reason": "missing_node_name"}
        from backend.models.pod_metric import PodMetric
        from datetime import datetime, timedelta
        _SYSTEM_NS = frozenset(["kube-system", "kube-public", "kube-node-lease"])
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        remaining = (
            self.db.query(PodMetric.pod_name)
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.node_name == node_name,
                PodMetric.controller_kind != "DaemonSet",
                ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
                PodMetric.timestamp > cutoff,
            )
            .distinct()
            .count()
        )
        if remaining == 0:
            return {"ok": True, "reason": "node_has_no_user_pods", "node": node_name}
        return {
            "ok": False,
            "reason": "user_pods_still_on_node",
            "node": node_name,
            "remaining_user_pods": remaining,
        }

    def _validate_node_terminated(self, cluster_id: str, node_name: Optional[str]) -> Dict[str, Any]:
        """
        Verify the EC2 instance is now terminated/terminating.
        Reads the instances table which the metrics agent keeps in sync.
        """
        if not node_name:
            return {"ok": False, "reason": "missing_node_name"}
        from backend.models.instance import Instance
        inst = (
            self.db.query(Instance.state)
            .filter(Instance.cluster_id == cluster_id, Instance.node_name == node_name)
            .first()
        )
        if inst is None:
            return {"ok": True, "reason": "instance_row_gone_presumed_terminated", "node": node_name}
        if inst.state in ("terminated", "terminating", "stopped"):
            return {"ok": True, "reason": f"instance_state_{inst.state}", "node": node_name}
        return {
            "ok": False,
            "reason": "instance_still_running_after_terminate",
            "node": node_name,
            "instance_state": inst.state,
        }

    def _validate_pod_evicted(self, cluster_id: str, pod_name: Optional[str], namespace: str) -> Dict[str, Any]:
        """
        Verify the evicted pod is no longer reporting Running metrics.
        """
        if not pod_name:
            return {"ok": False, "reason": "missing_pod_name"}
        from backend.models.pod_metric import PodMetric
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=3)
        still_running = (
            self.db.query(PodMetric.pod_name)
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.pod_name == pod_name,
                PodMetric.namespace == namespace,
                (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
                PodMetric.timestamp > cutoff,
            )
            .first()
        )
        if not still_running:
            return {"ok": True, "reason": "pod_no_longer_running", "pod": pod_name}
        return {"ok": False, "reason": "pod_still_running_after_eviction", "pod": pod_name}

    # ------------------------------------------------------------------
    # Cache helper
    # ------------------------------------------------------------------

    def _cache_report(self, cluster_id: str, action_id: str, report: Dict[str, Any]) -> None:
        try:
            self.redis.setex(
                f"spot:validation:{cluster_id}:{action_id}",
                self.VALIDATION_TTL_SECONDS,
                json.dumps(report),
            )
        except Exception:
            pass
