"""
WebSocket utility helpers for pushing commands to connected cluster agents.

This module re-exports the shared active_connections dict and provides
push_command_to_cluster / is_cluster_connected helpers that other parts
of the backend can call without importing from api_gateway (avoids circular).
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lazily imported to avoid circular import — api_gateway sets this up first.
def _get_active_connections() -> Dict[str, Any]:
    """Return the active WebSocket connections dict from api_gateway."""
    try:
        from backend.core import api_gateway
        return api_gateway.active_connections
    except (ImportError, AttributeError):
        return {}


def is_cluster_connected(cluster_id: str) -> bool:
    """Return True if a WebSocket connection for cluster_id is currently active."""
    return cluster_id in _get_active_connections()


async def push_command_to_cluster(
    cluster_id: str,
    command: Dict[str, Any],
) -> bool:
    """
    Push a JSON command dict to a connected cluster agent over WebSocket.

    Returns True if the message was sent, False if the cluster is not connected
    or the send failed.

    Args:
        cluster_id: The cluster UUID.
        command: Dict to JSON-encode and send (must include 'type' key).
    """
    connections = _get_active_connections()
    ws = connections.get(cluster_id)
    if ws is None:
        logger.debug(f"[ws] push_command_to_cluster: cluster {cluster_id} not connected")
        return False
    try:
        await ws.send_text(json.dumps(command))
        logger.info(f"[ws] Pushed command type={command.get('type')} to cluster {cluster_id}")
        return True
    except Exception as exc:
        logger.warning(f"[ws] Failed to push command to cluster {cluster_id}: {exc}")
        # Remove stale connection
        connections.pop(cluster_id, None)
        return False


async def push_agent_action(cluster_id: str, action_id: str, action_type: str, payload: Dict) -> bool:
    """
    Convenience wrapper: push a standard 'command' message to the agent.

    Returns True on success.
    """
    command = {
        "type": "command",
        "action_id": action_id,
        "action_type": action_type,
        "payload": payload or {},
    }
    return await push_command_to_cluster(cluster_id, command)
