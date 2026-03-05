"""
Execution Engine Pipeline — End-to-End Command Orchestrator
=============================================================
Source: backend/workers/tasks/auto_rebalancer.py (execute_rebalancing_action)
        backend/api/agent_routes.py (WebSocket + HTTP polling handlers)
        agent/main.py (poll loop + WebSocket handler)
        agent/actuator.py (ActionActuator.execute_action_v2)

PURPOSE
-------
This module ties together all 6 execution steps into a single orchestrated
pipeline that moves a Decision Engine recommendation into real AWS/K8s changes.

PIPELINE OVERVIEW
------------------
The execution is SPLIT across two processes:

  BACKEND PROCESS (runs in Celery worker / FastAPI):
    Step 1: Action Queue     — Convert recommendation → 3 AgentAction DB records
    Step 2: Command Dispatch — Push commands to agent via WebSocket (or HTTP poll)

  AGENT PROCESS (runs inside Kubernetes cluster as DaemonSet pod):
    Step 3: K8s Actuator     — Cordon + Drain the source node
    Step 4: Karpenter Ctrl   — Patch NodePool CRD with target spot pool
    Step 5: Substitute Mgr   — Warm spare becomes ACTIVE (absorbs drained pods)
    Step 6: Result Reporter  — Send execution results back to backend

  BACKEND PROCESS (continues after agent reports):
    Step 6b: Process result  — Update DB, publish SSE, trigger EC2 termination

FULL EXECUTION SEQUENCE (with timing)
---------------------------------------

  t=0     Backend: Decision Engine selects target pool (c5.large in ap-south-1b)
  t=0     Backend: Check safety gates (stabilization lock, substitute state, cooldowns)
  t=0     Backend: Create 3 AgentActions in DB (CORDON → DRAIN → PATCH_NODEPOOL)
  t=0     Backend: Set instance rebalance cooldown (24h, prevents re-targeting)
  t=0     Backend: Push actions to agent via WebSocket (or wait for poll)

  t=1s    Agent:   Receive CORDON_NODE command for instance i-0abc123
  t=1s    Agent:   Resolve K8s node name (from spec.providerID containing i-0abc123)
  t=2s    Agent:   PATCH /api/v1/nodes/{name} → spec.unschedulable=True
  t=2s    Agent:   Report CORDON result → Backend updates DB

  t=3s    Agent:   Receive DRAIN_NODE command
  t=3s    Agent:   List all pods on the node (excluding daemonsets, mirror pods)
  t=3s    Agent:   For each pod: POST /api/v1/namespaces/{ns}/pods/{name}/eviction
  t=35s   Agent:   All pods evicted (30s grace period each, parallel)
  t=35s   Agent:   Report DRAIN result → Backend updates DB

  [Concurrent]
  t=0     Substitute Manager: Warm spare in READY state (pre-provisioned 24×7)
  t=35s   Warm spare: Evicted pods reschedule on warm spare immediately
           (spare already READY → no provisioning delay → ZERO DOWNTIME)
  t=35s   SubstituteManager: Warm spare transitions READY → ACTIVE (6h TTL)
  t=36s   SubstituteManager: Start prewarming NEXT warm spare (IDLE → PREWARMING)

  t=36s   Agent:   Receive PATCH_KARPENTER_NODEPOOL command
  t=36s   Agent:   PATCH Karpenter NodePool CRD requirements
           → instance_types: ["c5.large"], capacity_type: ["spot"], az: "ap-south-1b"
  t=37s   Agent:   Report PATCH result → Backend updates DB

  *** CURRENT GAP (pods are on warm spare + remaining on-demand nodes) ***

  [MISSING STEP — required for real spot migration]:
  t=38s   Backend: Terminate EC2 instance i-0abc123 (only if terminate_after_drain=True)
  t=39s   Karpenter: Detects pods may exceed remaining capacity → provisions c5.large spot
  t=90s   Karpenter: New c5.large spot node is K8s-READY
  t=90s   Scheduler: Pods move to new spot node (final home)
  t=90s   Warm spare: Pods leave → can release spare (transition ACTIVE → RELEASING → IDLE)

  t=0+    Backend: Publish SSE events to UI for real-time status updates

WHY THIS PIPELINE EXISTS (vs. direct K8s calls)
-------------------------------------------------
The backend CANNOT call the Kubernetes API directly because:
  - EKS cluster's K8s API server is in a PRIVATE subnet (VPC-internal)
  - Backend runs on a separate server (no VPN, no VPC peering by default)
  - The DaemonSet agent runs INSIDE the cluster with in-cluster kubeconfig

Solution: Queue-based command pattern
  - Backend writes commands to PostgreSQL (durable, auditable)
  - Agent polls or receives via WebSocket
  - Agent executes K8s operations using in-cluster credentials
  - Agent reports results back via HTTP

FAILURE MODES AND RECOVERY
-----------------------------
  CORDON fails:
    → DRAIN is NOT sent (would be pointless without cordon)
    → Release distributed lock
    → Mark RebalancingAction FAILED

  DRAIN fails (PDB blocking, unmanaged pods):
    → PATCH_NODEPOOL is NOT sent (no point — node still has pods)
    → Un-cordon the node (restore to schedulable)
    → Release distributed lock
    → Increment failure counter (circuit breaker)

  PATCH_NODEPOOL fails:
    → Log error, release lock
    → Karpenter won't be directed to target pool
    → BUT node is already drained → pods are on warm spare (zero downtime)
    → Next auto-rebalance cycle will retry

  Agent disconnects mid-execution:
    → Actions remain in PICKED_UP state (not COMPLETED)
    → After 30-minute timeout, backend can retry
    → WebSocket reconnect triggers re-push of pending actions

DISTRIBUTED LOCK
-----------------
A distributed lock prevents concurrent drains on the same cluster:
  Key: lock:node_action:{cluster_id}
  TTL: 180 seconds

Only one drain sequence runs at a time per cluster.
This prevents:
  - Two nodes being drained simultaneously (pods might have nowhere to go)
  - Auto-rebalancer + manual action conflicting
  - Race conditions in the substitute manager
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Execution Pipeline Entry Point (backend-side)
# ---------------------------------------------------------------------------

class ExecutionPipeline:
    """
    Orchestrates the full execution flow for a pool switch recommendation.

    Instantiated by auto_rebalancer.py Celery task when the Decision Engine
    returns an approved recommendation.

    Usage:
        pipeline = ExecutionPipeline(db, redis)
        result = pipeline.execute(recommendation)
    """

    def __init__(self, db_session, redis_client):
        """
        Args:
            db_session:   SQLAlchemy session for DB operations
            redis_client: Redis connection for locking + state
        """
        self.db = db_session
        self.redis = redis_client

    def execute(self, recommendation: dict, cluster) -> dict:
        """
        Execute a pool switch recommendation end-to-end.

        Called after the Decision Engine approves a recommendation.
        Creates the 3 AgentAction records and dispatches them.

        Args:
            recommendation: Decision Engine output dict with keys:
                            - selected_pool (pool object with instance_type, az)
                            - source_instance (Instance ORM object)
                            - rebalancing_action_id (str UUID)
                            - cluster_id (str)
            cluster:        Cluster ORM object

        Returns:
            {
                "queued": bool,
                "actions_created": int,
                "deferred_reason": str or None,
                "actions": [action_id, ...]
            }
        """
        from ml_model.execution_engine.step_01_action_queue import (
            check_safety_gates,
            create_pool_switch_actions,
            set_instance_rebalance_cooldown,
        )

        cluster_id    = cluster.id
        rebalancing_id = recommendation.get("rebalancing_action_id")
        instance       = recommendation.get("source_instance")
        pool           = recommendation.get("selected_pool")

        # Step 1a: Safety gates (stabilization lock, substitute state, cooldowns)
        can_proceed, defer_reason = check_safety_gates(
            self.db, cluster_id, rebalancing_id
        )
        if not can_proceed:
            return {
                "queued":           False,
                "deferred_reason":  defer_reason,
                "actions_created":  0,
                "actions":          [],
            }

        # Step 1b: Acquire distributed lock (one drain per cluster at a time)
        lock_key = f"lock:node_action:{cluster_id}"
        lock_acquired = self.redis.set(lock_key, "1", nx=True, ex=180)
        if not lock_acquired:
            return {
                "queued":           False,
                "deferred_reason":  "Distributed lock held by concurrent operation",
                "actions_created":  0,
                "actions":          [],
            }

        try:
            # Step 1c: Create 3 AgentAction records in DB
            actions = create_pool_switch_actions(
                db_session            = self.db,
                cluster_id            = cluster_id,
                rebalancing_action_id = rebalancing_id,
                instance_id           = instance.instance_id,
                source_instance_type  = instance.instance_type,
                source_az             = instance.availability_zone,
                target_instance_type  = pool.instance_type,
                target_az             = pool.az,
            )
            self.db.commit()

            # Step 1d: Set 24h cooldown on the instance (prevent re-targeting)
            set_instance_rebalance_cooldown(self.redis, instance.instance_id)

            action_ids = [str(a.id) for a in actions]

            # Step 2: Dispatch commands to agent (WebSocket or HTTP polling)
            # (WebSocket push is handled by AgentCommandDispatcher in agent_routes.py)
            # If agent is connected via WebSocket, actions are pushed immediately.
            # If not connected, agent will pick them up on next HTTP poll (≤10s).

            return {
                "queued":           True,
                "actions_created":  len(actions),
                "actions":          action_ids,
                "deferred_reason":  None,
            }

        except Exception as e:
            # Release lock on failure so next cycle can try
            self.redis.delete(lock_key)
            return {
                "queued":           False,
                "actions_created":  0,
                "deferred_reason":  f"Exception: {str(e)}",
                "actions":          [],
            }


# ---------------------------------------------------------------------------
# Agent-side execution loop (runs inside K8s cluster)
# ---------------------------------------------------------------------------

class AgentExecutionLoop:
    """
    Main execution loop running inside the agent DaemonSet pod.

    Continuously polls for or receives commands, executes K8s operations,
    and reports results back to the backend.

    The actual implementation is in:
      agent/main.py        → startup and WebSocket connection
      agent/websocket_client.py → WebSocket reconnect loop
      agent/actuator.py   → ActionActuator.execute_action_v2()
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str):
        """
        Args:
            backend_url: Backend API base URL (e.g., https://api.example.com)
            api_key:     Agent API key for authentication
            cluster_id:  This agent's cluster ID
        """
        self.backend_url = backend_url
        self.api_key     = api_key
        self.cluster_id  = cluster_id

    def process_command(self, command: dict) -> dict:
        """
        Execute a single command received from the backend.

        Dispatches to the appropriate K8s operation based on action_type.
        Returns result dict to be sent back to backend.

        Command types and their handler:
          CORDON_NODE            → actuator.cordon_node(node_name)
          DRAIN_NODE             → actuator.drain_node(node_name, force, grace_period)
          PATCH_KARPENTER_NODEPOOL → actuator.patch_karpenter_nodepool(name, instance_types, ...)
          INSTALL_KARPENTER      → actuator.install_karpenter(cluster_name, region)
          UNINSTALL_KARPENTER    → actuator.uninstall_karpenter()
          EVICT_POD              → actuator.evict_pod(namespace, pod_name, grace_period)
          LABEL_NODE             → actuator.label_node(node_name, labels, remove)
          UPDATE_DEPLOYMENT      → actuator.update_deployment(namespace, name, replicas, image)

        Args:
            command: {
                "action_id":   "uuid",
                "action_type": "drain_node",
                "payload":     { "instance_id": "i-0abc", ... }
            }

        Returns:
            {
                "success": bool,
                "result":  { ... action-specific result fields ... },
                "error":   None or "error message string"
            }
        """
        action_type = command.get("action_type", "").upper()
        payload     = command.get("payload", {})

        # The actual dispatch is in agent/actuator.py → execute_action_v2()
        # Reference: each action_type maps to an actuator method

        ACTION_DISPATCH = {
            "CORDON_NODE":             "_execute_cordon",
            "DRAIN_NODE":              "_execute_drain",
            "PATCH_KARPENTER_NODEPOOL": "_execute_karpenter_patch",
            "INSTALL_KARPENTER":       "_execute_karpenter_install",
            "EVICT_POD":               "_execute_evict_pod",
            "LABEL_NODE":              "_execute_label_node",
            "UPDATE_DEPLOYMENT":       "_execute_update_deployment",
        }

        handler_name = ACTION_DISPATCH.get(action_type)
        if not handler_name:
            return {
                "success": False,
                "result":  {},
                "error":   f"Unknown action_type: {action_type}"
            }

        # Handler is called on the ActionActuator instance in agent/actuator.py
        # Here we just document the dispatch pattern
        return {
            "success": True,
            "result":  {"dispatched_to": handler_name, "payload": payload},
            "error":   None,
        }


# ---------------------------------------------------------------------------
# Execution pipeline summary (for documentation / logging)
# ---------------------------------------------------------------------------

EXECUTION_STEPS = [
    {
        "step": 1,
        "name": "Action Queue",
        "process": "Backend (Celery)",
        "file": "01_action_queue.py",
        "description": (
            "Convert Decision Engine recommendation into 3 AgentAction DB records: "
            "CORDON → DRAIN → PATCH_KARPENTER_NODEPOOL. "
            "Run safety gates first (stabilization lock, substitute state, cooldowns)."
        ),
    },
    {
        "step": 2,
        "name": "Command Dispatcher",
        "process": "Backend (FastAPI)",
        "file": "02_command_dispatcher.py",
        "description": (
            "Push queued actions to agent via WebSocket (real-time). "
            "Fallback: agent polls GET /api/v1/agents/actions/pending every 10s."
        ),
    },
    {
        "step": 3,
        "name": "K8s Actuator",
        "process": "Agent (in-cluster DaemonSet)",
        "file": "03_k8s_actuator.py",
        "description": (
            "Execute Kubernetes operations: cordon node (make unschedulable), "
            "drain node (evict all non-daemonset pods gracefully). "
            "Resolves K8s node name from EC2 instance_id via spec.providerID."
        ),
    },
    {
        "step": 4,
        "name": "Karpenter Controller",
        "process": "Agent (in-cluster DaemonSet)",
        "file": "04_karpenter_controller.py",
        "description": (
            "Patch Karpenter NodePool CRD to target the desired spot pool "
            "(instance_type, AZ, capacity_type). "
            "Karpenter provisions new spot node when pods become PENDING."
        ),
    },
    {
        "step": 5,
        "name": "Substitute Manager",
        "process": "Backend (Celery + Redis)",
        "file": "05_substitute_manager.py",
        "description": (
            "Warm spare transitions READY → ACTIVE. "
            "Drained pods land on the pre-provisioned spare instantly (zero downtime). "
            "New warm spare is immediately prewarmed to maintain 24×7 readiness."
        ),
    },
    {
        "step": 6,
        "name": "Result Reporter",
        "process": "Agent → Backend",
        "file": "06_result_reporter.py",
        "description": (
            "Agent POSTs execution results to backend. "
            "Backend updates AgentAction DB records and publishes SSE events. "
            "If terminate_after_drain=True: backend calls EC2 TerminateInstances "
            "to force pods PENDING → trigger real Karpenter spot provisioning."
        ),
    },
]


def print_pipeline_summary():
    """Print a human-readable summary of all execution pipeline steps."""
    print("\n=== Spot Optimizer — Execution Engine Pipeline ===\n")
    for step in EXECUTION_STEPS:
        print(f"  Step {step['step']}: {step['name']}")
        print(f"    Process: {step['process']}")
        print(f"    File:    {step['file']}")
        print(f"    What:    {step['description'][:80]}...")
        print()
