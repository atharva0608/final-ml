#!/usr/bin/env python3
"""
WebSocket Client Module

This module provides real-time bidirectional communication with the backend:
- Receive action commands
- Receive configuration updates
- Send status updates
- Handle ping/pong for connection health
- Automatic reconnection with exponential backoff
"""

import os
import sys
import time
import json
import logging
import asyncio
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import websockets
from websockets.exceptions import WebSocketException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebSocketClient:
    """
    WebSocket client for real-time communication with backend.
    """

    def __init__(self, backend_ws_url: str, api_key: str, cluster_id: str,
                 agent_id: str):
        """
        Initialize the WebSocket client.

        Args:
            backend_ws_url: WebSocket URL of the backend
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
            agent_id: Unique identifier for this agent
        """
        self.backend_ws_url = backend_ws_url
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.agent_id = agent_id

        self.websocket = None
        self.running = False
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 0  # 0 = unlimited retries

        # Message handlers
        self.message_handlers = {}
        self.default_handler = None

        # Reference to actuator for executing commands received via WebSocket
        self.actuator = None

        # BUG-1/N6 fix: Separate queues by criticality.
        # Critical messages (action results, state transitions) must never be dropped.
        # Best-effort messages (metrics, heartbeats) use a bounded ring buffer.
        import collections
        import queue
        self.critical_queue = queue.Queue()       # unbounded — never drop action results
        self.metrics_buffer = collections.deque(maxlen=200)  # ring buffer — oldest dropped when full

        # Legacy buffer kept for backward compat but no longer used for new messages
        self.message_buffer = []
        self.max_buffer_size = 1000

        # BUG-2 fix: Track current in-progress action for context recovery on reconnect
        self._current_action_id = None

        logger.info(f"WebSocketClient initialized for agent: {agent_id}")

    def register_handler(self, message_type: str, handler: Callable):
        """
        Register a handler for a specific message type.

        Args:
            message_type: Type of message to handle
            handler: Callable that takes message data as argument
        """
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")

    def set_default_handler(self, handler: Callable):
        """
        Set default handler for unrecognized message types.

        Args:
            handler: Callable that takes message data as argument
        """
        self.default_handler = handler
        logger.info("Set default message handler")

    def set_actuator(self, actuator):
        """
        Wire in the ActionActuator so the WebSocket handler can execute commands.
        Must be called before run().
        """
        self.actuator = actuator
        logger.info("ActionActuator wired into WebSocketClient")

    async def connect(self):
        """
        Establish WebSocket connection to backend.
        Backend endpoint: /ws/cluster/{cluster_id}?agent_id={agent_id}
        """
        # Normalize base URL: strip trailing /ws if present, then append /ws/cluster/{id}
        base = self.backend_ws_url.rstrip('/')
        if f"/ws/cluster/{self.cluster_id}" in base:
            url = f"{base}?agent_id={self.agent_id}"
        else:
            if base.endswith('/ws'):
                base = base[:-3]  # strip /ws
            url = f"{base}/ws/cluster/{self.cluster_id}?agent_id={self.agent_id}"

        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }

        try:
            logger.info(f"Connecting to WebSocket: {url}")
            self.websocket = await websockets.connect(
                url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
            logger.info("WebSocket connection established")

            # Reset reconnection parameters
            self.reconnect_delay = 1
            self.reconnect_attempts = 0

            # Send buffered messages
            await self.flush_buffer()

            return True

        except WebSocketException as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to WebSocket: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """
        Close WebSocket connection.
        """
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

        self.websocket = None

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to the backend.

        Args:
            message: Message dictionary

        Returns:
            True if successful, False otherwise
        """
        # Add metadata
        message['cluster_id'] = self.cluster_id
        message['agent_id'] = self.agent_id
        message['timestamp'] = datetime.utcnow().isoformat()

        message_json = json.dumps(message)

        if self.websocket and not self.websocket.closed:
            try:
                await self.websocket.send(message_json)
                logger.debug(f"Sent message: {message.get('type')}")
                return True
            except WebSocketException as e:
                logger.error(f"Failed to send message: {e}")
                self.buffer_message(message)
                return False
        else:
            # Buffer message if not connected
            self.buffer_message(message)
            return False

    def buffer_message(self, message: Dict[str, Any]):
        """
        Buffer a message for later sending.
        BUG-1/N6 fix: Critical messages (action_result, action_heartbeat,
        action_still_running) go to an unbounded queue that is never dropped.
        Everything else goes to a bounded ring buffer (metrics, heartbeats).
        """
        msg_type = message.get("type", "")
        if msg_type in ("action_result", "action_heartbeat", "action_still_running"):
            self.critical_queue.put(message)
            logger.debug(f"Buffered critical message ({msg_type}). Queue size: {self.critical_queue.qsize()}")
        else:
            self.metrics_buffer.append(message)
            logger.debug(f"Buffered best-effort message ({msg_type}). Buffer size: {len(self.metrics_buffer)}")

    async def flush_buffer(self):
        """
        Send all buffered messages.
        BUG-1/N6 fix: Critical messages (action results) sent first,
        then best-effort metrics. Critical messages are never dropped.
        """
        _critical_count = self.critical_queue.qsize()
        _metrics_count = len(self.metrics_buffer)
        _legacy_count = len(self.message_buffer)
        _total = _critical_count + _metrics_count + _legacy_count
        if _total == 0:
            return

        logger.info(
            f"Flushing buffered messages: {_critical_count} critical, "
            f"{_metrics_count} metrics, {_legacy_count} legacy"
        )

        # BUG-2 fix: If an action is still running, notify backend immediately
        if self._current_action_id:
            await self.send_message({
                "type": "action_still_running",
                "action_id": self._current_action_id,
                "timestamp": datetime.utcnow().isoformat(),
            })

        # 1. Critical messages first (action results — must not be lost)
        while not self.critical_queue.empty():
            try:
                msg = self.critical_queue.get_nowait()
            except Exception:
                break
            try:
                await self.send_message(msg)
            except Exception as e:
                logger.error(
                    "flush_buffer: failed to send critical message type=%s, "
                    "re-queuing. Error: %s",
                    msg.get("type"), e
                )
                self.critical_queue.put(msg)  # re-queue so it isn't lost
                break  # stop flush — connection may not be ready yet

        # 2. Best-effort metrics buffer
        for msg in list(self.metrics_buffer):
            await self.send_message(msg)
        self.metrics_buffer.clear()

        # 3. Legacy buffer (backward compat)
        if self.message_buffer:
            messages_to_send = self.message_buffer.copy()
            self.message_buffer.clear()
            for message in messages_to_send:
                await self.send_message(message)

    async def handle_message(self, message_json: str):
        """
        Handle incoming message from backend.

        Args:
            message_json: JSON string of message
        """
        try:
            message = json.loads(message_json)
            message_type = message.get('type')

            logger.debug(f"Received message: {message_type}")

            # Route to appropriate handler
            if message_type in self.message_handlers:
                handler = self.message_handlers[message_type]
                await self._run_handler(handler, message)
            elif self.default_handler:
                await self._run_handler(self.default_handler, message)
            else:
                logger.warning(f"No handler for message type: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    async def _run_handler(self, handler: Callable, message: Dict[str, Any]):
        """
        Run a message handler (sync or async).

        Args:
            handler: Handler function
            message: Message data
        """
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                # Run sync handler in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler, message)
        except Exception as e:
            logger.error(f"Error in message handler: {e}", exc_info=True)

    async def handle_command(self, message: Dict[str, Any]):
        """
        Handle a command pushed by the backend.

        Backend format:
          {"type": "command", "action_id": "...", "action_type": "cordon_node", "payload": {...}}

        Executes the action via actuator (inside the cluster), then sends result back:
          {"type": "action_result", "action_id": "...", "success": true/false, "result": {...}}
        """
        action_id = message.get('action_id')
        action_type = message.get('action_type', '')
        payload = message.get('payload', {})

        logger.info(f"[ws] Received command: action_id={action_id}, type={action_type}")

        if not action_id or not action_type:
            logger.warning(f"[ws] Malformed command (missing action_id or action_type): {message}")
            return

        if not self.actuator:
            logger.error("[ws] No actuator wired — cannot execute command. Call set_actuator() first.")
            await self.send_message({
                'type': 'action_result',
                'action_id': action_id,
                'success': False,
                'error': 'Agent actuator not initialized',
            })
            return

        # Execute synchronously in a thread pool to avoid blocking the async loop
        # N5 fix: Start heartbeat thread during action execution
        _hb_stop = threading.Event()
        _hb_thread = None
        _rebalancing_action_id = payload.get('rebalancing_action_id')
        if _rebalancing_action_id and self.actuator:
            _hb_thread = threading.Thread(
                target=self.actuator._action_heartbeat_loop,
                args=(str(_rebalancing_action_id), _hb_stop),
                daemon=True,
            )
            _hb_thread.start()

        # BUG-2 fix: Track current action for context recovery on reconnect
        self._current_action_id = _rebalancing_action_id or action_id

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self.actuator.execute_action_v2, action_type, payload
            )
        except Exception as e:
            result = {'success': False, 'message': str(e)}
            logger.error(f"[ws] Exception executing {action_type}: {e}", exc_info=True)
        finally:
            self._current_action_id = None
            if _hb_thread:
                _hb_stop.set()
                _hb_thread.join(timeout=5)

        # Report result back to backend via WebSocket
        _result_msg = {
            'type': 'action_result',
            'action_id': action_id,
            'success': result.get('success', False),
            'result': result,
            'error': result.get('message') if not result.get('success') else None,
        }
        ws_sent = await self.send_message(_result_msg)

        # BUG-1 fix: If WebSocket send failed, try HTTP fallback so the backend
        # always learns about the action outcome (prevents 45-min cluster lock).
        if not ws_sent and self.actuator:
            try:
                import requests as _req
                _req.post(
                    f"{self.actuator.backend_url}/api/v1/agents/actions/{action_id}/result",
                    json=_result_msg,
                    headers={"Authorization": f"Bearer {self.actuator.api_key}"},
                    timeout=10,
                )
                logger.info(f"[ws] Action result for {action_id} sent via HTTP fallback")
            except Exception as _http_err:
                logger.error(f"[ws] HTTP fallback also failed for action {action_id}: {_http_err}")
                # Message is already in critical_queue — will flush on reconnect

        logger.info(f"[ws] Command {action_id} ({action_type}) done: success={result.get('success')}")

    async def handle_action_command(self, message: Dict[str, Any]):
        """Legacy handler kept for backward compatibility — delegates to handle_command."""
        await self.handle_command(message)

    async def handle_config_update(self, message: Dict[str, Any]):
        """
        Handle configuration update from backend.

        Args:
            message: Message containing configuration
        """
        logger.info("Received configuration update")

        config = message.get('config', {})

        # Apply configuration (this would need to be implemented based on requirements)
        logger.info(f"Configuration update: {config}")

    async def handle_ping(self, message: Dict[str, Any]):
        """
        Handle ping from backend.

        Args:
            message: Ping message
        """
        logger.debug("Received ping")

        # Send pong
        await self.send_message({
            'type': 'pong',
            'timestamp': datetime.utcnow().isoformat()
        })

    async def receive_loop(self):
        """
        Main loop for receiving messages.
        """
        while self.running:
            if not self.websocket or self.websocket.closed:
                logger.warning("WebSocket not connected, waiting...")
                await asyncio.sleep(1)
                continue

            try:
                message = await self.websocket.recv()
                await self.handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}", exc_info=True)
                break

    async def reconnect_loop(self):
        """
        Loop for maintaining connection with reconnection logic.
        Retries indefinitely with exponential backoff (capped at 60s).
        Counter resets on each successful connection so transient failures
        don't accumulate across long sessions.
        """
        while self.running:
            if not self.websocket or self.websocket.closed:
                self.reconnect_attempts += 1
                logger.info(f"Attempting reconnection (attempt {self.reconnect_attempts})")

                connected = await self.connect()

                if connected:
                    logger.info("Reconnection successful, resetting backoff")
                    self.reconnect_attempts = 0
                    # Start receive loop
                    asyncio.create_task(self.receive_loop())
                else:
                    # Exponential backoff capped at max_reconnect_delay
                    delay = min(
                        self.reconnect_delay * (2 ** min(self.reconnect_attempts, 6)),
                        self.max_reconnect_delay
                    )
                    logger.info(f"Reconnection failed, retrying in {delay}s")
                    await asyncio.sleep(delay)

            await asyncio.sleep(1)

    async def run(self):
        """
        Run the WebSocket client.
        """
        self.running = True
        logger.info("Starting WebSocket client")

        # Register built-in handlers
        self.register_handler('command', self.handle_command)           # v2: backend pushes commands
        self.register_handler('action_command', self.handle_action_command)  # v1: legacy compat
        self.register_handler('config_update', self.handle_config_update)
        self.register_handler('ping', self.handle_ping)

        # Initial connection
        connected = await self.connect()

        if connected:
            # Start tasks
            receive_task = asyncio.create_task(self.receive_loop())
            reconnect_task = asyncio.create_task(self.reconnect_loop())

            # Wait for tasks
            await asyncio.gather(receive_task, reconnect_task)
        else:
            logger.error("Initial connection failed")

        logger.info("WebSocket client stopped")

    async def stop(self):
        """
        Stop the WebSocket client.
        """
        logger.info("Stopping WebSocket client...")
        self.running = False

        # Send disconnect message
        await self.send_message({
            'type': 'disconnect',
            'reason': 'shutdown'
        })

        await self.disconnect()


async def main():
    """Main entry point for testing."""
    backend_ws_url = os.getenv('BACKEND_WS_URL', 'ws://localhost:8000/ws')
    api_key = os.getenv('API_KEY', 'test-key')
    cluster_id = os.getenv('CLUSTER_ID', 'test-cluster')
    agent_id = os.getenv('AGENT_ID', 'test-agent')

    client = WebSocketClient(backend_ws_url, api_key, cluster_id, agent_id)

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        await client.stop()


if __name__ == '__main__':
    asyncio.run(main())
