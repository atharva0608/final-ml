"""
Step 2 (Execution): Command Dispatcher — Backend → Agent Communication
========================================================================
Source: backend/api/agent_routes.py
        agent/websocket_client.py
        agent/main.py

PURPOSE
-------
The Command Dispatcher is the BRIDGE between the backend's action queue
(PostgreSQL AgentAction records) and the Kubernetes agent DaemonSet.

There are TWO communication paths:

  Path A (PRIMARY): WebSocket Push
  -----------------------------------
  The agent maintains a persistent WebSocket connection to the backend.
  When a new AgentAction is queued (by 01_action_queue.py), the backend
  immediately pushes the command to the agent via WebSocket.

  Backend endpoint: ws://<backend>/ws/cluster/{cluster_id}
  Agent connects at startup (agent/main.py → websocket_client.py)

  Advantages:
    - Real-time (no polling delay)
    - Efficient (single connection, bidirectional)
    - Immediate feedback (agent sends result back on same connection)

  Path B (FALLBACK): HTTP Polling
  ----------------------------------
  If the WebSocket connection drops or is unavailable, the agent falls back
  to polling the backend's REST API every 10 seconds (ACTION_POLL_INTERVAL).

  Agent polls: GET /api/v1/agents/actions/pending
  Agent reports: POST /api/v1/agents/actions/{id}/result

  Advantages:
    - Works when WebSocket is blocked (some firewalls, ngrok limitations)
    - Simpler to debug (HTTP logs are standard)

  Disadvantages:
    - Up to 10-second latency before action is picked up
    - More HTTP overhead (constant polling)

AGENT ACTION LIFECYCLE
------------------------
  Created → PENDING (in DB, waiting for agent pickup)
  Picked up → PICKED_UP (agent acknowledged receipt via WebSocket ACK)
  Executing → (agent running the K8s operation)
  Completed → COMPLETED (agent reported success)
  Failed → FAILED (agent reported error, with error message)

COMMAND PAYLOAD FORMAT (v2 protocol)
--------------------------------------
Commands are sent as JSON:
  {
    "action_id": "uuid",
    "action_type": "CORDON_NODE" | "DRAIN_NODE" | "PATCH_KARPENTER_NODEPOOL" | ...,
    "payload": {
      ... action-specific fields ...
      "instance_id": "i-0abc123",       -- for CORDON/DRAIN (node resolution)
      "instance_type": "m5.large",      -- fallback for node resolution
      "az": "ap-south-1a",              -- fallback for node resolution
      "nodepool_name": "default",       -- for PATCH_KARPENTER_NODEPOOL
      "instance_types": ["c5.large"],   -- for PATCH_KARPENTER_NODEPOOL
    }
  }

NODE NAME RESOLUTION (critical)
---------------------------------
The backend stores EC2 instance IDs (e.g. "i-0abc123def456").
The Kubernetes API needs node NAMES (e.g. "ip-10-0-1-100.ap-south-1.compute.internal").

The agent resolves this using TWO methods (in priority order):

  Method 1: spec.providerID lookup (preferred)
    Every EKS node has: spec.providerID = "aws://ap-south-1a/i-0abc123def456"
    The agent scans all nodes and finds the one containing the instance ID.
    Code: agent/actuator.py → _find_node_by_instance_id()

  Method 2: Label selector fallback
    Karpenter-provisioned nodes have:
      node.kubernetes.io/instance-type=m5.large
      topology.kubernetes.io/zone=ap-south-1a
    The agent queries by these labels if instance_id lookup fails.
    Code: agent/actuator.py → _find_node_name()

AUTHENTICATION
---------------
All agent↔backend communication uses:
  - Bearer token (API key) in Authorization header
  - ngrok-skip-browser-warning header (if using ngrok tunnel)
  - HMAC signatures on action payloads (verify command integrity)

SECURITY NOTE
--------------
The HMAC signature verification (agent/actuator.py → verify_signature)
uses a shared secret key stored in the agent's environment variables.
This prevents replay attacks and unauthorized command injection.
"""

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# WebSocket Command Push (backend-side)
# ---------------------------------------------------------------------------

class AgentCommandDispatcher:
    """
    Backend-side dispatcher that sends queued AgentActions to the cluster agent.

    In production: instantiated in agent_routes.py WebSocket handler.
    Maintains a mapping of cluster_id → WebSocket connection.
    """

    def __init__(self, db_session, redis_client):
        """
        Args:
            db_session:   SQLAlchemy DB session
            redis_client: Redis connection
        """
        self.db = db_session
        self.redis = redis_client

        # Map of cluster_id → active WebSocket connection
        # In FastAPI, this is managed by SSE/WebSocket endpoint
        self._connections: dict = {}

    def register_connection(self, cluster_id: str, websocket):
        """
        Register a new WebSocket connection from an agent.

        Called when the agent's WebSocket connects to:
          ws://<backend>/ws/cluster/{cluster_id}

        Args:
            cluster_id: Cluster the agent belongs to
            websocket:  FastAPI WebSocket object
        """
        self._connections[cluster_id] = websocket

    def deregister_connection(self, cluster_id: str):
        """Remove WebSocket connection when agent disconnects."""
        self._connections.pop(cluster_id, None)

    async def push_pending_actions(self, cluster_id: str) -> int:
        """
        Push all PENDING AgentActions to the connected agent.

        Called after a new action is queued (by 01_action_queue.py)
        to immediately notify the agent without waiting for polling.

        Args:
            cluster_id: Target cluster ID

        Returns:
            Number of actions pushed (0 if agent not connected)
        """
        websocket = self._connections.get(cluster_id)
        if not websocket:
            return 0  # Agent not connected, will pick up via HTTP polling

        # Fetch pending actions from DB
        from backend.models.agent_action import AgentAction, AgentActionStatus
        pending_actions = self.db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status == AgentActionStatus.PENDING
        ).order_by(AgentAction.created_at).all()

        pushed = 0
        for action in pending_actions:
            command = {
                "action_id": action.id,
                "action_type": action.action_type.value,
                "payload": action.payload or {}
            }
            try:
                await websocket.send_json(command)
                # Mark as picked up (agent acknowledged via WebSocket)
                action.status = AgentActionStatus.PICKED_UP
                action.picked_up_at = __import__("datetime").datetime.utcnow()
                pushed += 1
            except Exception as e:
                # WebSocket broken — fall back to HTTP polling
                self.deregister_connection(cluster_id)
                break

        self.db.commit()
        return pushed


# ---------------------------------------------------------------------------
# HTTP Polling Endpoints (agent-side, proxied via backend API)
# ---------------------------------------------------------------------------

def get_pending_actions_for_agent(db_session, cluster_id: str) -> List[Dict]:
    """
    Return pending AgentActions for an agent's HTTP poll request.

    Called by: GET /api/v1/agents/actions/pending
    Agent polls this every ACTION_POLL_INTERVAL seconds (default: 10s).

    Flow:
      1. Agent sends GET with Authorization: Bearer {api_key}
      2. Backend returns list of PENDING commands
      3. Agent marks each as PICKED_UP and executes

    Args:
        db_session: SQLAlchemy DB session
        cluster_id: Agent's cluster ID (from auth token)

    Returns:
        List of command dicts ready for agent consumption:
        [
          {
            "action_id": "uuid",
            "action_type": "cordon_node",   -- lowercase for agent compatibility
            "payload": {...}
          },
          ...
        ]
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from datetime import datetime

    pending = db_session.query(AgentAction).filter(
        AgentAction.cluster_id == cluster_id,
        AgentAction.status == AgentActionStatus.PENDING
    ).order_by(AgentAction.created_at).limit(10).all()  # Max 10 at a time

    commands = []
    for action in pending:
        commands.append({
            "action_id": action.id,
            "action_type": action.action_type.value.lower(),  # Agent expects lowercase
            "payload": action.payload or {}
        })
        # Mark as picked up
        action.status = AgentActionStatus.PICKED_UP
        action.picked_up_at = datetime.utcnow()

    db_session.commit()
    return commands


def record_action_result(
    db_session,
    redis_client,
    action_id: str,
    success: bool,
    result: dict,
    error: Optional[str] = None
) -> bool:
    """
    Record an action result reported by the agent.

    Called by: POST /api/v1/agents/actions/{action_id}/result
    Agent calls this after executing each action.

    Args:
        db_session:  SQLAlchemy DB session
        redis_client: Redis connection
        action_id:   AgentAction UUID
        success:     Whether the action succeeded
        result:      Full result dict from agent (has evicted, nodes_cordoned, etc.)
        error:       Error message if success=False

    Returns:
        True if action record was found and updated
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from datetime import datetime

    action = db_session.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not action:
        return False

    action.status = AgentActionStatus.COMPLETED if success else AgentActionStatus.FAILED
    action.completed_at = datetime.utcnow()
    action.result = result
    action.error_message = error

    db_session.commit()

    # After action completes: publish via SSE for real-time UI updates
    try:
        import json
        event = json.dumps({
            "type": "agent_action_completed",
            "action_id": action_id,
            "success": success,
            "cluster_id": action.cluster_id
        })
        redis_client.publish(f"sse:cluster:{action.cluster_id}", event)
    except Exception:
        pass

    return True
