"""
Step 6 (Execution): Result Reporter — Agent → Backend Feedback Loop
====================================================================
Source: agent/main.py, agent/websocket_client.py
        backend/api/agent_routes.py (POST /api/v1/agents/actions/{id}/result)

PURPOSE
-------
After the Kubernetes Actuator (Step 3) performs a K8s operation, the result
is sent back to the backend. This closes the feedback loop:

  Backend → (AgentAction queue) → Agent → (K8s operation) → (result) → Backend

This result reporting serves three purposes:
  1. UPDATE the AgentAction record in PostgreSQL (status, timestamps, result JSON)
  2. PUBLISH a real-time SSE event so the UI updates without polling
  3. TRIGGER any downstream actions (e.g., after DRAIN completes → terminate EC2)

WHY RESULTS MATTER
-------------------
The execution is asynchronous:
  - Backend queues CORDON → DRAIN → PATCH_KARPENTER_NODEPOOL (3 actions)
  - Agent executes them one-by-one
  - Each action's result tells the backend what actually happened

Without results:
  - Backend doesn't know if drain succeeded (so can't safely terminate EC2)
  - UI would show "PENDING" forever
  - Retry logic couldn't trigger on failures

RESULT PAYLOAD FORMAT
----------------------
Agent sends POST /api/v1/agents/actions/{action_id}/result with:
  {
    "success": true,
    "result": {
      "action_type": "drain_node",
      "node_name": "ip-10-0-1-100.ap-south-1.compute.internal",
      "evicted": 7,
      "failed": 0,
      "errors": [],
      "duration_seconds": 42
    },
    "error": null
  }

On failure:
  {
    "success": false,
    "result": { "action_type": "drain_node", "errors": ["PDB blocking pod my-app-xyz"] },
    "error": "PDB violation: 429 after 5 retries for pod my-app-xyz"
  }

SSE EVENT AFTER COMPLETION
-----------------------------
After recording the result, the backend publishes to Redis pub/sub:
  Channel: sse:cluster:{cluster_id}
  Message: {
    "type": "agent_action_completed",
    "action_id": "uuid",
    "success": true,
    "cluster_id": "cluster-uuid"
  }

The frontend SSE listener picks this up and refreshes the relevant dashboard
sections (e.g., rebalancing status, node list).

DRAIN RESULT → EC2 TERMINATION (critical for real spot migration)
------------------------------------------------------------------
The current implementation queues 3 actions: CORDON → DRAIN → PATCH_NODEPOOL.
But after drain, pods reschedule on OTHER existing on-demand nodes.
They are NOT pending (other nodes have capacity), so Karpenter does NOT provision.

THE FIX (not yet implemented):
  After DRAIN_NODE completes successfully:
    1. Call AWS EC2 TerminateInstances API on the drained instance
    2. Pods from that node are now on existing OD nodes
    3. Those OD nodes now have less capacity
    4. Eventually pods on those OD nodes can't fit → become PENDING
    5. Karpenter sees PENDING pods → provisions spot node per NodePool spec

  Better approach: Also cordon the OTHER on-demand nodes simultaneously,
  so all pods are forced PENDING at once → Karpenter provisions all at once.

STATUS TRANSITIONS TRIGGERED BY RESULTS
-----------------------------------------
  Action result COMPLETED:
    CORDON_NODE     → logs "node cordoned", sets cordoned_at timestamp
    DRAIN_NODE      → logs "node drained", triggers EC2 termination (if enabled)
    PATCH_NODEPOOL  → logs "Karpenter ready for spot", marks rebalancing cycle done

  Action result FAILED:
    Any action      → marks RebalancingAction as FAILED
                    → releases distributed lock (lock:node_action:{cluster_id})
                    → triggers stabilization lock (prevents immediate retry)
                    → sends alert if circuit breaker threshold hit
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Action Status Constants (must match backend/models/agent_action.py)
# ---------------------------------------------------------------------------

ACTION_STATUS_PENDING    = "PENDING"
ACTION_STATUS_PICKED_UP  = "PICKED_UP"
ACTION_STATUS_COMPLETED  = "COMPLETED"
ACTION_STATUS_FAILED     = "FAILED"


# ---------------------------------------------------------------------------
# SSE Event Types
# ---------------------------------------------------------------------------

SSE_EVENT_ACTION_COMPLETED  = "agent_action_completed"
SSE_EVENT_ACTION_FAILED     = "agent_action_failed"
SSE_EVENT_REBALANCE_DONE    = "rebalancing_cycle_complete"


# ---------------------------------------------------------------------------
# Result payload builders (agent-side, before sending to backend)
# ---------------------------------------------------------------------------

def build_drain_result(
    node_name: str,
    evicted: int,
    failed: int,
    errors: list,
    duration_seconds: float,
    success: bool = None
) -> dict:
    """
    Build the result payload for a DRAIN_NODE action.

    Called by agent/actuator.py after drain_node() completes.
    Sent via POST /api/v1/agents/actions/{id}/result.

    Args:
        node_name:        K8s node name that was drained
        evicted:          Number of pods successfully evicted
        failed:           Number of pods that could not be evicted
        errors:           List of error strings for failed evictions
        duration_seconds: Time taken for the drain operation
        success:          Explicitly set, or derived from failed == 0

    Returns:
        Result dict to include in the POST body
    """
    if success is None:
        success = failed == 0
    return {
        "action_type":       "drain_node",
        "node_name":         node_name,
        "evicted":           evicted,
        "failed":            failed,
        "errors":            errors,
        "duration_seconds":  round(duration_seconds, 2),
    }


def build_cordon_result(node_name: str, success: bool) -> dict:
    """
    Build the result payload for a CORDON_NODE action.

    Args:
        node_name: K8s node name that was cordoned
        success:   Whether the PATCH /api/v1/nodes/{name} succeeded

    Returns:
        Result dict to include in the POST body
    """
    return {
        "action_type": "cordon_node",
        "node_name":   node_name,
        "cordoned":    success,
    }


def build_karpenter_patch_result(nodepool_name: str, instance_types: list,
                                  az: Optional[str], success: bool) -> dict:
    """
    Build the result payload for a PATCH_KARPENTER_NODEPOOL action.

    Args:
        nodepool_name:  Karpenter NodePool name (e.g. "default")
        instance_types: Instance types set in the requirements
        az:             AZ set in the requirements (if any)
        success:        Whether the PATCH CRD call succeeded

    Returns:
        Result dict to include in the POST body
    """
    return {
        "action_type":   "patch_karpenter_nodepool",
        "nodepool_name": nodepool_name,
        "instance_types": instance_types,
        "az":            az,
        "patched":       success,
    }


# ---------------------------------------------------------------------------
# Backend-side: Process incoming result from agent
# ---------------------------------------------------------------------------

def process_action_result(
    db_session,
    redis_client,
    action_id: str,
    success: bool,
    result: dict,
    error: Optional[str] = None
) -> dict:
    """
    Process a result reported by the agent for a completed action.

    This is the backend handler for:
      POST /api/v1/agents/actions/{action_id}/result

    Steps:
      1. Load AgentAction from DB
      2. Mark status = COMPLETED or FAILED
      3. Store result JSON and timestamps
      4. Publish SSE event for UI refresh
      5. Check if this result should trigger downstream actions
      6. Return summary

    Args:
        db_session:   SQLAlchemy DB session
        redis_client: Redis connection
        action_id:    AgentAction UUID
        success:      Whether the K8s operation succeeded
        result:       Full result dict from agent
        error:        Error message if success=False

    Returns:
        {"processed": bool, "action_type": str, "cluster_id": str}
    """
    import json
    from datetime import datetime
    from backend.models.agent_action import AgentAction, AgentActionStatus

    action = db_session.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not action:
        return {"processed": False, "reason": "action_not_found"}

    # Update DB record
    action.status = (
        AgentActionStatus.COMPLETED if success else AgentActionStatus.FAILED
    )
    action.completed_at = datetime.utcnow()
    action.result = result
    action.error_message = error
    db_session.commit()

    cluster_id = action.cluster_id
    action_type = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)

    # Publish SSE event for real-time UI update
    try:
        event_type = SSE_EVENT_ACTION_COMPLETED if success else SSE_EVENT_ACTION_FAILED
        event = json.dumps({
            "type":       event_type,
            "action_id":  action_id,
            "action_type": action_type,
            "success":    success,
            "cluster_id": cluster_id,
        })
        redis_client.publish(f"sse:cluster:{cluster_id}", event)
    except Exception:
        pass  # SSE failure must not block result recording

    return {
        "processed":   True,
        "action_type": action_type,
        "cluster_id":  cluster_id,
        "success":     success,
    }


def check_if_rebalancing_complete(db_session, rebalancing_action_id: str) -> bool:
    """
    Check whether ALL 3 AgentActions for a rebalancing cycle have completed.

    After the final PATCH_KARPENTER_NODEPOOL action completes, the rebalancing
    cycle is considered done (Karpenter is now configured to provision spot nodes).

    Args:
        db_session:            SQLAlchemy DB session
        rebalancing_action_id: RebalancingAction ID to check

    Returns:
        True if all 3 actions (CORDON, DRAIN, PATCH_NODEPOOL) are COMPLETED
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus

    actions = db_session.query(AgentAction).filter(
        AgentAction.payload["rebalancing_action_id"].astext == rebalancing_action_id
    ).all()

    if len(actions) < 3:
        return False  # Not all 3 actions created yet

    return all(
        a.status == AgentActionStatus.COMPLETED
        for a in actions
    )


# ---------------------------------------------------------------------------
# Drain Result → EC2 Termination (next critical step for real spot migration)
# ---------------------------------------------------------------------------

def should_terminate_after_drain(redis_client, cluster_id: str) -> bool:
    """
    Check whether the cluster config requires EC2 termination after drain.

    Context: Simply draining a node does NOT trigger Karpenter provisioning.
    Pods from the drained node reschedule onto other existing on-demand nodes
    (they still have capacity), so they are never PENDING.

    Karpenter only provisions when pods are PENDING (can't be scheduled).
    To force this, the drained EC2 instance must be TERMINATED.

    This function checks a per-cluster config flag that enables post-drain
    EC2 termination for real spot migration.

    Args:
        redis_client: Redis connection
        cluster_id:   Cluster identifier

    Returns:
        True if the cluster should terminate EC2 instances after drain
        (vs. just drain and rely on expiry / manual cleanup)
    """
    try:
        import json
        config_raw = redis_client.get(f"karpenter_config:{cluster_id}")
        if config_raw:
            config = json.loads(config_raw)
            return bool(config.get("terminate_after_drain", False))
    except Exception:
        pass
    return False


def get_ec2_termination_payload(action_result: dict, action_payload: dict) -> Optional[dict]:
    """
    Extract the EC2 instance ID from a completed DRAIN_NODE result
    to prepare for post-drain EC2 termination.

    After drain completes, the backend can optionally call:
      boto3.ec2.terminate_instances(InstanceIds=[instance_id])

    This forces pods to be PENDING (no node to land on), which triggers
    Karpenter to provision a new spot node per the NodePool requirements
    set by the subsequent PATCH_KARPENTER_NODEPOOL action.

    Args:
        action_result:  The result dict returned by the agent
        action_payload: The original payload from the AgentAction record
                        (contains instance_id, instance_type, az)

    Returns:
        {"instance_id": "i-0abc123", "region": "ap-south-1"}
        or None if instance_id is not available
    """
    instance_id = action_payload.get("instance_id")
    if not instance_id:
        return None
    region = action_payload.get("region", "ap-south-1")
    return {"instance_id": instance_id, "region": region}
