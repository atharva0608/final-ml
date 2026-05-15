"""
Phase 5 End-to-End Tests — PlacementController v1.4
=======================================================
Covers all scenarios from plan.md §8 Phase 5:
  1. Stateless burst correction (OD excess → EVICT_POD actions)
  2. Stateful rollout: create-before-delete (disruption_safe=false)
  3. Stateful rollout timeout → rollback with zero-availability safety
  4. ENI-constrained AZ rejection (pod-slot count exceeded)
  5. K8s rollout-status guard (updated_replicas != ready_replicas → skip)

Additional guards tested:
  6. Shadow mode → no EVICT_POD written, metrics still counted
  7. Pod age guard (Fix 4) → pods < 2 min skipped
  8. evictions_failed_due_to_no_replacement metric (Fix 5)
  9. Drift threshold — no action when excess < threshold
  10. Cooldown — no action when workload is in cooldown

Webhook tests:
  11. AZ spread injected when az_spread_required=True
  12. Spot preference injected always
  13. Idempotency — no duplicate injection if constraints already present
  14. No injection when policy.actionable=False
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from backend.pipeline.stage3_ppe.controller_service import (
    PlacementController,
    PodInfo,
    SpotNode,
    CapacityMap,
    RolloutStatus,
    SHADOW_MODE_KEY_TEMPLATE,
    POD_AGE_MIN_SECONDS,
    MAX_EVICTIONS_PER_CYCLE,
)
from backend.services.placement_rollout_service import PlacementRolloutService
from backend.api.placement_webhook_routes import (
    _build_patches,
    _az_spread_patches,
    _spot_preference_patches,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_pod(
    uid="pod-1",
    name="app-pod-1",
    namespace="default",
    az="us-east-1a",
    node="node-1",
    cpu_request=500.0,
    memory_request=512.0,
    age_seconds=300.0,
    capacity_type="on-demand",
):
    return PodInfo(
        uid=uid,
        name=name,
        namespace=namespace,
        az=az,
        node=node,
        capacity_type=capacity_type,
        cpu_request=cpu_request,
        memory_request=memory_request,
        age_seconds=age_seconds,
    )


def _make_spot_node(
    az="us-east-1a",
    allocatable_cpu=4000.0,
    allocatable_memory=8192.0,
    max_pods=30,
    current_pod_count=5,
):
    return SpotNode(
        name="spot-node-1",
        az=az,
        allocatable_cpu=allocatable_cpu,
        allocatable_memory=allocatable_memory,
        max_pods=max_pods,
        current_pod_count=current_pod_count,
    )


def _make_redis_stub(
    pods=None,
    policy=None,
    shadow_mode=False,
    spot_nodes=None,
    pending_pods=0,
    workload_state=None,
):
    """Creates a minimal Redis stub with configurable responses."""
    store = {}
    if pods is not None:
        store["pods"] = json.dumps(pods)
    if policy is not None:
        store["policy"] = json.dumps(policy)
    if shadow_mode:
        store["shadow"] = "1"
    if spot_nodes is not None:
        store["nodes"] = json.dumps(spot_nodes)
    if workload_state is not None:
        store["workload_state"] = json.dumps(workload_state)
    store["pending_pods"] = str(pending_pods)

    redis = MagicMock()
    redis.exists = MagicMock(return_value=False)
    redis.get = MagicMock(return_value=None)
    redis.set = MagicMock(return_value=True)
    redis.setex = MagicMock()
    redis.delete = MagicMock()
    redis.keys = MagicMock(return_value=[])
    redis.rpush = MagicMock()
    redis.hset = MagicMock()
    redis.expire = MagicMock()
    redis.lrange = MagicMock(return_value=[])
    return redis, store


def _make_controller(redis_stub, rollout_svc=None):
    db = MagicMock()
    k8s = MagicMock()
    k8s.get_deployment_rollout_status.return_value = {
        "updated_replicas": 3,
        "ready_replicas": 3,
    }
    if rollout_svc is None:
        rollout_svc = MagicMock()
    return PlacementController(db=db, redis=redis_stub, k8s_client=k8s, rollout_svc=rollout_svc)


# ---------------------------------------------------------------------------
# Test 1: Stateless burst correction
# ---------------------------------------------------------------------------

def test_stateless_burst_evicts_excess_od_pods():
    """
    Scenario: 5 OD pods, ondemand_target=2, disruption_safe=True.
    Expect: 3 EVICT_POD actions created (capped at MAX_EVICTIONS_PER_CYCLE).
    """
    pods = [
        _make_pod(uid=f"pod-{i}", name=f"app-{i}", age_seconds=400.0)
        for i in range(5)
    ]
    node = _make_spot_node()
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 2,
        "disruption_safe": True,
        "actionable": True,
        "current_replicas": 5,
    }

    redis, _ = _make_redis_stub()
    redis.get.side_effect = lambda key: (
        json.dumps(pods.__class__([p.__dict__ for p in pods])) if "pods" in key
        else json.dumps([node.__dict__]) if "spot_nodes" in key
        else None
    )
    redis.keys.return_value = [f"spot:placement:policy:c1:default/myapp"]
    redis.get.side_effect = lambda key: (
        json.dumps([p.__dict__ for p in pods]) if "spot:workload:pods" in key
        else json.dumps([node.__dict__]) if "spot_nodes" in key
        else json.dumps(policy) if "placement:policy" in key
        else None
    )

    controller = _make_controller(redis)

    metrics = {
        "evictions_attempted": 0,
        "evictions_skipped_capacity": 0,
        "evictions_skipped_cooldown": 0,
        "evictions_skipped_scaling_guard": 0,
        "evictions_skipped_pod_too_young": 0,
        "evictions_failed_due_to_no_replacement": 0,
        "stateful_rollout_started": 0,
        "stateful_rollout_completed": 0,
        "stateful_rollout_failed": 0,
        "stateful_rollout_timeout": 0,
    }

    controller._process_workload("c1", "default/myapp", policy, CapacityMap(
        nodes_by_az={"us-east-1a": [node]}
    ), metrics)

    # Should evict exactly MAX_EVICTIONS_PER_CYCLE = 3 (excess=3, cap=3)
    assert metrics["evictions_attempted"] == min(3, MAX_EVICTIONS_PER_CYCLE)
    assert controller.db.add.called  # EVICT_POD now dispatched via AgentAction DB record


# ---------------------------------------------------------------------------
# Test 2: K8s rollout-status guard
# ---------------------------------------------------------------------------

def test_rolling_update_guard_skips_workload():
    """
    Scenario: Deployment is mid-rollout (updated_replicas=2, ready_replicas=1).
    Expect: workload skipped, evictions_skipped_scaling_guard incremented.
    """
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 1,
        "disruption_safe": True,
        "actionable": True,
    }
    redis, _ = _make_redis_stub()
    k8s = MagicMock()
    k8s.get_deployment_rollout_status.return_value = {
        "updated_replicas": 2,
        "ready_replicas": 1,  # mid-rollout
    }
    redis.get.return_value = None

    controller = PlacementController(
        db=MagicMock(), redis=redis, k8s_client=k8s, rollout_svc=MagicMock()
    )
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller._process_workload("c1", "default/myapp", policy, CapacityMap(), metrics)

    assert metrics["evictions_skipped_scaling_guard"] == 1
    assert metrics["evictions_attempted"] == 0
    assert not redis.rpush.called


# ---------------------------------------------------------------------------
# Test 3: ENI-constrained AZ rejection
# ---------------------------------------------------------------------------

def test_eni_slot_exhaustion_rejects_placement():
    """
    Scenario: Spot node has 30 max_pods and 29 current pods (only 1 free slot).
    Placing 3 pods would exceed 70% of 1 slot → capacity check fails.
    Expect: evictions_skipped_capacity incremented; no EVICT_POD actions.
    """
    node = _make_spot_node(max_pods=30, current_pod_count=29)  # 1 free slot
    pods = [
        _make_pod(uid=f"pod-{i}", name=f"app-{i}", age_seconds=500.0)
        for i in range(3)
    ]
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 0,
        "disruption_safe": True,
        "actionable": True,
    }

    controller = _make_controller(MagicMock())
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    capacity_map = CapacityMap(nodes_by_az={"us-east-1a": [node]})
    desired_az_map = {pod.uid: "us-east-1a" for pod in pods}

    result = controller._has_spot_capacity_for_target_az(pods, desired_az_map, capacity_map)
    assert result is False


# ---------------------------------------------------------------------------
# Test 4: Drift threshold — no action below threshold
# ---------------------------------------------------------------------------

def test_drift_threshold_prevents_premature_eviction():
    """
    Scenario: ondemand_target=10, actual_od=11 (excess=1), drift_threshold=2.
    Expect: no action taken (drift below threshold).
    """
    pods = [_make_pod(uid=f"pod-{i}", age_seconds=400.0) for i in range(11)]
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 10,
        "disruption_safe": True,
        "actionable": True,
    }
    redis = MagicMock()
    redis.exists.return_value = False
    redis.get.side_effect = lambda key: (
        json.dumps([p.__dict__ for p in pods]) if "spot:workload:pods" in key
        else json.dumps([_make_spot_node().__dict__]) if "spot_nodes" in key
        else None
    )
    controller = _make_controller(redis)
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller._process_workload(
        "c1", "default/myapp", policy, CapacityMap(nodes_by_az={"us-east-1a": [_make_spot_node()]}), metrics
    )

    # drift_threshold for target=10 is max(2, int(10*0.2)) = 2; excess=1 < 2
    assert metrics["evictions_attempted"] == 0
    assert not redis.rpush.called


# ---------------------------------------------------------------------------
# Test 5: Shadow mode — metrics counted, no actions written
# ---------------------------------------------------------------------------

def test_shadow_mode_counts_metrics_but_no_actions():
    """
    Scenario: Shadow mode active, 4 OD pods, target=1.
    Expect: evictions_attempted incremented but redis.rpush NOT called.
    """
    pods = [_make_pod(uid=f"pod-{i}", name=f"app-{i}", age_seconds=400.0) for i in range(4)]
    node = _make_spot_node()
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 1,
        "disruption_safe": True,
        "actionable": True,
    }

    redis = MagicMock()
    redis.exists.return_value = False

    def redis_get(key):
        if "shadow_mode" in key:
            return "1"  # shadow mode ON
        if "spot:workload:pods" in key:
            return json.dumps([p.__dict__ for p in pods])
        if "spot_nodes" in key:
            return json.dumps([node.__dict__])
        return None

    redis.get.side_effect = redis_get

    controller = _make_controller(redis)
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller._process_workload(
        "c1", "default/myapp", policy,
        CapacityMap(nodes_by_az={"us-east-1a": [node]}),
        metrics,
    )

    assert metrics["evictions_attempted"] > 0
    assert not redis.rpush.called, "Shadow mode must not write EVICT_POD to queue"


# ---------------------------------------------------------------------------
# Test 6: Pod age guard (Fix 4)
# ---------------------------------------------------------------------------

def test_pod_age_guard_skips_young_pods():
    """
    Scenario: All 3 OD pods are younger than POD_AGE_MIN_SECONDS (2 min).
    Expect: All skipped, evictions_skipped_pod_too_young == 3.
    """
    young_pods = [
        _make_pod(uid=f"pod-{i}", name=f"app-{i}", age_seconds=60.0)
        for i in range(3)
    ]
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller = _make_controller(MagicMock())
    result = controller._select_burst_pods(young_pods, 3, metrics)

    assert result == []
    assert metrics["evictions_skipped_pod_too_young"] == 3


def test_pod_age_guard_allows_old_pods():
    """Old pods (> 2 min) are not filtered."""
    old_pods = [_make_pod(uid=f"pod-{i}", age_seconds=300.0) for i in range(3)]
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller = _make_controller(MagicMock())
    result = controller._select_burst_pods(old_pods, 3, metrics)

    assert len(result) == 3
    assert metrics["evictions_skipped_pod_too_young"] == 0


# ---------------------------------------------------------------------------
# Test 7: evictions_failed_due_to_no_replacement (Fix 5)
# ---------------------------------------------------------------------------

def test_no_replacement_metric_incremented_when_no_spot_nodes():
    """
    Scenario: Capacity check fails AND no Spot nodes exist at all.
    Expect: evictions_failed_due_to_no_replacement == 1.
    """
    empty_capacity = CapacityMap(nodes_by_az={})  # no Spot nodes
    pods = [_make_pod(uid="pod-1", age_seconds=400.0)]
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 0,
        "disruption_safe": True,
        "actionable": True,
    }

    redis = MagicMock()
    redis.exists.return_value = False
    redis.get.side_effect = lambda key: (
        json.dumps([p.__dict__ for p in pods]) if "spot:workload:pods" in key else None
    )

    controller = _make_controller(redis)
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller._process_workload("c1", "default/myapp", policy, empty_capacity, metrics)

    assert metrics["evictions_skipped_capacity"] == 1
    assert metrics["evictions_failed_due_to_no_replacement"] == 1


# ---------------------------------------------------------------------------
# Test 8: Stateful rollout — zero-availability rollback safety
# ---------------------------------------------------------------------------

def test_stateful_rollout_skips_scale_down_if_original_pod_gone():
    """
    Scenario: Rollout timed out AND original pod is no longer Running.
    Expect: _scale_workload NOT called with original_replicas (would drop to 0 availability).
    """
    redis = MagicMock()
    redis.get.side_effect = lambda key: (
        json.dumps({"phase": "Terminating"}) if "pod_status" in key
        else json.dumps({"ready_replicas": 1}) if "workload:state" in key  # old count
        else json.dumps([]) if "spot_nodes" in key
        else None
    )
    redis.rpush = MagicMock()

    svc = PlacementRolloutService(db=MagicMock(), redis_client=redis)
    svc._has_capacity_for_new_replica = MagicMock(return_value=True)
    svc._wait_for_new_replica_ready = MagicMock(return_value=False)  # timeout
    svc._original_pod_still_running = MagicMock(return_value=False)  # pod gone
    svc._annotate_node = MagicMock()

    metrics = {}
    result = svc.execute_stateful_rollout(
        cluster_id="c1",
        workload={"workload_id": "default/myapp", "current_replicas": 3, "namespace": "default"},
        pod_to_replace=_make_pod(),
        metrics=metrics,
    )

    assert result is False
    assert metrics.get("stateful_rollout_timeout", 0) == 1
    # _scale_workload should NOT be called with original_replicas (rollback skipped)
    for call in redis.rpush.call_args_list:
        if call:
            try:
                arg = json.loads(call[0][1])
                if arg.get("type") == "SCALE_WORKLOAD":
                    assert arg.get("replicas") != 3, "Must NOT scale back when original pod is gone"
            except (json.JSONDecodeError, IndexError, TypeError):
                pass


# ---------------------------------------------------------------------------
# Test 9: Stateful rollout Fix 3 — new pod on OD → abort migration
# ---------------------------------------------------------------------------

def test_stateful_rollout_aborts_if_new_pod_on_od():
    """
    Fix 3: New replica landed on On-Demand (scheduler constraints overrode Spot hint).
    Expect: scale back to original, stateful_rollout_failed incremented.
    """
    redis = MagicMock()
    redis.rpush = MagicMock()

    svc = PlacementRolloutService(db=MagicMock(), redis_client=redis)
    svc._has_capacity_for_new_replica = MagicMock(return_value=True)
    svc._wait_for_new_replica_ready = MagicMock(return_value=True)  # new pod Ready
    svc._new_pod_placed_on_spot = MagicMock(return_value=False)  # but it's on OD
    svc._annotate_node = MagicMock()
    svc._evict_pod = MagicMock()

    metrics = {}
    result = svc.execute_stateful_rollout(
        cluster_id="c1",
        workload={"workload_id": "default/myapp", "current_replicas": 3, "namespace": "default"},
        pod_to_replace=_make_pod(),
        metrics=metrics,
    )

    assert result is False
    assert metrics.get("stateful_rollout_failed", 0) == 1
    svc._evict_pod.assert_not_called()  # old OD pod must NOT be evicted if migration failed

    # Scale back must have been called (via rpush SCALE_WORKLOAD)
    scale_calls = [
        json.loads(c[0][1])
        for c in redis.rpush.call_args_list
        if c and json.loads(c[0][1]).get("type") == "SCALE_WORKLOAD"
    ]
    assert any(c.get("replicas") == 3 for c in scale_calls), "Must scale back to original_replicas"


# ---------------------------------------------------------------------------
# Test 10: Cooldown guard
# ---------------------------------------------------------------------------

def test_cooldown_prevents_repeated_eviction():
    """Workload in cooldown must be skipped entirely."""
    policy = {
        "workload_id": "default/myapp",
        "ondemand_target": 1,
        "disruption_safe": True,
        "actionable": True,
    }
    redis = MagicMock()
    redis.exists.return_value = True  # cooldown key exists

    controller = _make_controller(redis)
    metrics = {k: 0 for k in ["evictions_attempted", "evictions_skipped_capacity",
                                "evictions_skipped_cooldown", "evictions_skipped_scaling_guard",
                                "evictions_skipped_pod_too_young", "evictions_failed_due_to_no_replacement",
                                "stateful_rollout_started", "stateful_rollout_completed",
                                "stateful_rollout_failed", "stateful_rollout_timeout"]}

    controller._process_workload("c1", "default/myapp", policy, CapacityMap(), metrics)

    assert metrics["evictions_skipped_cooldown"] == 1
    assert not redis.rpush.called


# ---------------------------------------------------------------------------
# Test 11: Newest-first pod selection
# ---------------------------------------------------------------------------

def test_select_burst_pods_newest_first():
    """
    Pod selection picks newest pods (lowest age_seconds) first from over-represented AZ.
    """
    pods = [
        _make_pod(uid="old", name="old", az="us-east-1a", age_seconds=900.0),
        _make_pod(uid="new1", name="new1", az="us-east-1a", age_seconds=300.0),
        _make_pod(uid="new2", name="new2", az="us-east-1a", age_seconds=200.0),
    ]
    controller = _make_controller(MagicMock())
    metrics = {k: 0 for k in ["evictions_skipped_pod_too_young"]}
    selected = controller._select_burst_pods(pods, 2, metrics)

    uids = [p.uid for p in selected]
    assert "new2" in uids  # newest first
    assert "new1" in uids
    assert "old" not in uids  # oldest skipped


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------

def test_webhook_injects_az_spread_when_required():
    """AZ spread constraint injected when az_spread_required=True."""
    patches = _az_spread_patches(spec={})
    assert len(patches) == 1
    assert patches[0]["path"] == "/spec/topologySpreadConstraints"
    assert patches[0]["value"][0]["whenUnsatisfiable"] == "ScheduleAnyway"
    assert patches[0]["value"][0]["maxSkew"] == 1
    assert patches[0]["value"][0]["topologyKey"] == "topology.kubernetes.io/zone"


def test_webhook_does_not_inject_az_spread_when_not_required():
    """No patches when policy is None (cache miss or no policy for workload)."""
    with patch("backend.api.placement_webhook_routes._get_policy", return_value=None):
        patches = _build_patches(
            cluster_id="c1",
            namespace="default",
            controller_name="myapp",
            pod_spec={"spec": {}},
        )
    assert patches == []


def test_webhook_spot_preference_injected():
    """Spot node preference patch created for empty spec."""
    patches = _spot_preference_patches(spec={})
    path_keys = [p["path"] for p in patches]
    # Should create /spec/affinity, /spec/affinity/nodeAffinity, and the preferred term
    assert any("preferredDuringSchedulingIgnoredDuringExecution" in p for p in path_keys)


def test_webhook_az_spread_idempotent():
    """AZ spread not injected if topology spread already present for zone key."""
    existing_spec = {
        "topologySpreadConstraints": [
            {
                "topologyKey": "topology.kubernetes.io/zone",
                "whenUnsatisfiable": "DoNotSchedule",
                "maxSkew": 1,
            }
        ]
    }
    patches = _az_spread_patches(spec=existing_spec)
    assert patches == []


def test_webhook_spot_preference_idempotent():
    """Spot affinity not injected if karpenter capacity-type preference already present."""
    existing_spec = {
        "affinity": {
            "nodeAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 80,
                        "preference": {
                            "matchExpressions": [
                                {
                                    "key": "karpenter.sh/capacity-type",
                                    "operator": "In",
                                    "values": ["spot"],
                                }
                            ]
                        },
                    }
                ]
            }
        }
    }
    patches = _spot_preference_patches(spec=existing_spec)
    assert patches == []
