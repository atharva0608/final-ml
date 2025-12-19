"""
WebSocket Connection Manager

Manages WebSocket connections for real-time log streaming.
"""

from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates

    Supports per-session log streaming for Sandbox Mode.
    """

    def __init__(self):
        # session_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """
        Accept a new WebSocket connection and subscribe to session

        Args:
            websocket: WebSocket connection
            session_id: Sandbox session ID to subscribe to
        """
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()

        self.active_connections[session_id].add(websocket)

        print(f"✓ WebSocket connected to session {session_id}")
        print(f"  Total connections for session: {len(self.active_connections[session_id])}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        """
        Remove a WebSocket connection

        Args:
            websocket: WebSocket connection to remove
            session_id: Session ID
        """
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)

            # Clean up empty session
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        print(f"✗ WebSocket disconnected from session {session_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """
        Send message to a specific WebSocket connection

        Args:
            message: Message to send (JSON string or dict)
            websocket: Target WebSocket connection
        """
        if isinstance(message, dict):
            message = json.dumps(message)

        await websocket.send_text(message)

    async def broadcast_to_session(self, session_id: str, message: dict):
        """
        Broadcast message to all connections subscribed to a session

        Args:
            session_id: Target session ID
            message: Message dict to broadcast
        """
        if session_id not in self.active_connections:
            return  # No active connections

        message_str = json.dumps(message)

        # Send to all connections (with error handling)
        dead_connections = set()

        for connection in self.active_connections[session_id]:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                print(f"Error sending to WebSocket: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for dead_conn in dead_connections:
            self.disconnect(dead_conn, session_id)

    async def send_log(self, session_id: str, log_type: str, message: str, level: str = "INFO"):
        """
        Send a log message to all connections subscribed to a session

        Args:
            session_id: Target session ID
            log_type: Log type (e.g., "SETUP", "SCRAPER", "DECISION")
            message: Log message
            level: Log level (INFO, WARNING, ERROR, SUCCESS)
        """
        await self.broadcast_to_session(session_id, {
            "type": "log",
            "log_type": log_type,
            "message": message,
            "level": level,
            "timestamp": asyncio.get_event_loop().time()
        })

    async def send_status(self, session_id: str, status: dict):
        """
        Send status update to session

        Args:
            session_id: Target session ID
            status: Status dict
        """
        await self.broadcast_to_session(session_id, {
            "type": "status",
            "data": status
        })

    def get_session_connection_count(self, session_id: str) -> int:
        """
        Get number of active connections for a session

        Args:
            session_id: Session ID

        Returns:
            Number of active connections
        """
        return len(self.active_connections.get(session_id, set()))

    # [ARCH-005] Enhanced WebSocket methods for live client updates

    async def send_live_switch(self, client_id: str, switch_event: dict):
        """
        [ARCH-005] Send real-time switch event to client's dashboard

        Args:
            client_id: Client ID
            switch_event: Switch event dictionary containing:
                - instance_id: Instance being switched
                - from_type: Current instance type
                - to_type: Target instance type
                - reason: Switch reason (spot-interruption, cost-optimization, etc.)
                - timestamp: Event timestamp
        """
        await self.broadcast_to_session(f"client:{client_id}", {
            "type": "live_switch",
            "data": switch_event
        })

    async def send_cluster_update(self, client_id: str, cluster_event: dict):
        """
        [ARCH-005] Send cluster state update to client

        Args:
            client_id: Client ID
            cluster_event: Cluster update containing topology changes
        """
        await self.broadcast_to_session(f"client:{client_id}", {
            "type": "cluster_update",
            "data": cluster_event
        })

    async def send_optimization_progress(self, client_id: str, progress: dict):
        """
        [ARCH-005] Send optimization progress update

        Args:
            client_id: Client ID
            progress: Progress dictionary with percentage, current_step, etc.
        """
        await self.broadcast_to_session(f"client:{client_id}", {
            "type": "optimization_progress",
            "data": progress
        })


# Global connection manager instance
manager = ConnectionManager()
