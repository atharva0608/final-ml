"""
Step 1 (Execution): Action Queue — AgentAction Creation
=========================================================
Source: backend/workers/tasks/auto_rebalancer.py (execute_rebalancing_action function)
Models: backend/models/agent_action.py

PURPOSE
-------
Convert a Decision Engine recommendation into concrete AgentAction records
in PostgreSQL. These records are the "command queue" that the K8s agent
polls (or receives via WebSocket) to know what operations to perform.

WHY A QUEUE INSTEAD OF DIRECT CALLS?
--------------------------------------
The Kubernetes cluster is INSIDE a VPC — the backend cannot make direct
K8s API calls to it. The agent DaemonSet runs inside the cluster with
in-cluster kubeconfig and polls the backend for pending actions.

This queue-based architecture:
  - Works with private Kubernetes API servers (no VPN needed)
  - Survives network interruptions (commands are persisted in DB)
  - Provides an audit trail of every action (AgentAction records)
  - Allows retry and deduplication logic
  - Enables one-at-a-time serialization (no concurrent drains)

TWO ACTIONS PER REBALANCE CYCLE + DIRECT K8S PATCH
----------------------------------------------------
For each on-demand → spot migration, 2 AgentActions are created in sequence,
and the Karpenter NodePool is patched directly via the K8s API:

  1. CORDON_NODE
     Payload: { instance_id, instance_type, az, rebalancing_action_id }
     Effect:  Marks node as unschedulable. New pods won't land here.
              Existing pods keep running until drained.

  2. DRAIN_NODE
     Payload: { instance_id, instance_type, az, ignore_daemonsets=True,
                grace_period_seconds=30, rebalancing_action_id }
     Effect:  Gracefully evicts all non-daemonset pods from the node.
              Pods reschedule on remaining on-demand nodes.
              After drain: node is empty but still EC2-running.

  Direct K8s API call (KarpenterService.add_allowed_instance_type):
     Effect:  Patches the Karpenter NodePool CRD directly via the K8s API
              to add the target instance type. No agent action needed.
              When the old node is terminated (causing pods to be PENDING),
              Karpenter will provision a new node matching these requirements.

SAFETY GATES BEFORE QUEUE
---------------------------
Before creating actions, three safety gates are checked:

  Gate 1: Stabilization Lock (5-min cross-system quiet period)
    Prevents two systems (auto-rebalancer + right-sizer) acting simultaneously.
    Redis Key: spot:stabilization_lock:{cluster_id}

  Gate 2: Substitute Mutual Exclusion
    If SubstituteManager is PREWARMING or RELEASING, don't drain the same node.
    Redis Key: spot:substitute:state:{cluster_id}
    READY state = warm spare is standing by (safe to drain, spare will absorb pods)

  Gate 3: Resize Cooldown
    If right-sizing just executed for this cluster, wait before rebalancing.
    Redis Key: spot:cooldown:action:resize:{cluster_id}

  Gate 4: Distributed Lock (per cluster)
    Serializes all K8s operations on a cluster. One drain at a time.
    Key: lock:node_action:{cluster_id} (timeout: 1200s / 20 min)

INSTANCE COOLDOWN
------------------
After queuing actions for an instance, a 24-hour Redis key is set:
  Key: spot:rebalanced:instance:{instance_id}
This prevents the auto-rebalancer from re-targeting the same instance
before AWS sync updates the DB with the new spot lifecycle.
"""

from datetime import datetime
from typing import Optional


# AgentAction types (must match backend/models/agent_action.py AgentActionType enum)
CORDON_NODE = "CORDON_NODE"
DRAIN_NODE = "DRAIN_NODE"
EVICT_POD = "EVICT_POD"
LABEL_NODE = "LABEL_NODE"
UPDATE_DEPLOYMENT = "UPDATE_DEPLOYMENT"
INSTALL_KARPENTER = "INSTALL_KARPENTER"
UNINSTALL_KARPENTER = "UNINSTALL_KARPENTER"


def create_pool_switch_actions(
    db_session,
    cluster_id: str,
    rebalancing_action_id: str,
    instance_id: str,
    source_instance_type: str,
    source_az: str,
    target_instance_type: str,
    target_az: str,
    nodepool_name: str = "default"
) -> list:
    """
    Create the 2 AgentAction records needed for a pool switch and patch
    the Karpenter NodePool directly via the K8s API.

    Called by execute_rebalancing_action() after all safety gates pass.
    The agent executes CORDON + DRAIN in DB-creation order. The NodePool
    is patched directly via KarpenterService (no agent action needed).

    Args:
        db_session:           SQLAlchemy DB session
        cluster_id:           Target cluster ID
        rebalancing_action_id: Parent RebalancingAction ID (for cross-reference)
        instance_id:          EC2 instance ID of the source node (e.g. "i-0abc123")
        source_instance_type: e.g. "m5.large"
        source_az:            e.g. "ap-south-1a"
        target_instance_type: e.g. "c5.large" (Karpenter provisions this)
        target_az:            e.g. "ap-south-1b" (target AZ for new spot node)
        nodepool_name:        Karpenter NodePool to patch (default: "default")

    Returns:
        List of AgentAction ORM objects (already added to session, not committed)

    Note:
        Caller must call db_session.commit() after this function.
        Actions are linked by rebalancing_action_id for audit trail.
    """
    from backend.models.agent_action import AgentAction, AgentActionType

    # Action 1: Cordon the source node (make it unschedulable)
    # The agent resolves the actual K8s node name from instance_id via providerID
    cordon_action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.CORDON_NODE,
        payload={
            "instance_id": instance_id,
            "instance_type": source_instance_type,
            "az": source_az,
            "rebalancing_action_id": rebalancing_action_id,
        }
    )

    # Action 2: Drain the source node (evict all pods gracefully)
    drain_action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.DRAIN_NODE,
        payload={
            "instance_id": instance_id,
            "instance_type": source_instance_type,
            "az": source_az,
            "ignore_daemonsets": True,         # Always skip daemonset pods (they can't move)
            "grace_period_seconds": 30,        # Give pods 30s to shut down gracefully
            "rebalancing_action_id": rebalancing_action_id,
        }
    )

    # Step 3: Patch Karpenter NodePool directly via K8s API
    # This tells Karpenter: when you need to provision a new node, use THIS instance type+AZ
    # Karpenter will only actually create the node when pods are PENDING (after termination)
    # No agent action needed — we call the K8s API directly from the backend
    from backend.services.karpenter_service import KarpenterService
    KarpenterService.add_allowed_instance_type(
        cluster_id=cluster_id,
        nodepool_name=nodepool_name,
        instance_type=target_instance_type,
    )

    db_session.add(cordon_action)
    db_session.add(drain_action)

    return [cordon_action, drain_action]


def check_safety_gates(db_session, cluster_id: str, action_id: str) -> tuple:
    """
    Run all pre-execution safety gates before creating action records.

    Returns:
        (can_proceed, defer_reason)
        can_proceed=True  → create actions and execute
        can_proceed=False → defer action with defer_reason
    """
    from backend.core.redis_client import get_redis_client
    from backend.services.cooldown_controller import CooldownController

    redis_client = get_redis_client()
    cooldown = CooldownController(redis_client)

    # Gate 1: Stabilization lock (5-min cross-system quiet period)
    is_locked, remaining = cooldown.is_stabilization_locked(cluster_id)
    if is_locked:
        return False, f"Stabilization lock active ({remaining}s remaining)"

    # Gate 2: Substitute mutual exclusion
    sub_state_raw = redis_client.get(f"spot:substitute:state:{cluster_id}")
    sub_state = (sub_state_raw.decode("utf-8") if isinstance(sub_state_raw, bytes) else sub_state_raw) or "IDLE"
    if sub_state in ("PREWARMING", "RELEASING"):
        return False, f"Substitute in state {sub_state} — deferred to avoid conflict"

    # Gate 3: Resize cooldown (right-sizer just ran, give it time)
    if redis_client.exists(f"spot:cooldown:action:resize:{cluster_id}"):
        return False, "Resize cooldown active — right-sizing is mid-execution"

    return True, None


def set_instance_rebalance_cooldown(redis_client, instance_id: str, ttl_seconds: int = 86400):
    """
    Set a 24-hour cooldown for a specific EC2 instance after rebalancing.

    This prevents the auto-rebalancer from immediately re-targeting the same
    instance before AWS sync updates the DB with the new spot lifecycle.

    After EC2 terminates and Karpenter provisions a replacement spot node,
    the AWS sync will update the instance lifecycle in DB to SPOT — then
    this cooldown is no longer needed (instance has been converted).

    Args:
        redis_client: Redis connection
        instance_id:  EC2 instance ID (e.g. "i-0abc123" or truncated "ip-10-0-1-100")
        ttl_seconds:  Cooldown duration (default: 86400 = 24 hours)
    """
    cooldown_key = f"spot:rebalanced:instance:{instance_id}"
    redis_client.setex(cooldown_key, ttl_seconds, "1")


def is_instance_in_cooldown(redis_client, instance_id: str) -> bool:
    """
    Check if an instance has been recently rebalanced.

    Called before creating new actions for an instance to prevent
    re-targeting the same node in the next cycle.

    Args:
        redis_client: Redis connection
        instance_id:  EC2 instance ID

    Returns:
        True if in cooldown (skip this instance), False if eligible
    """
    cooldown_key = f"spot:rebalanced:instance:{instance_id}"
    return bool(redis_client.exists(cooldown_key))
