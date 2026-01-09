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
        self.max_reconnect_attempts = 10

        # Message handlers
        self.message_handlers = {}
        self.default_handler = None

        # Message buffer for when disconnected
        self.message_buffer = []
        self.max_buffer_size = 1000

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

    async def connect(self):
        """
        Establish WebSocket connection to backend.
        """
        # Build connection URL with authentication
        url = f"{self.backend_ws_url}?cluster_id={self.cluster_id}&agent_id={self.agent_id}"

        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }

        try:
            logger.info(f"Connecting to WebSocket: {self.backend_ws_url}")
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

        Args:
            message: Message dictionary
        """
        if len(self.message_buffer) < self.max_buffer_size:
            self.message_buffer.append(message)
            logger.debug(f"Buffered message. Buffer size: {len(self.message_buffer)}")
        else:
            logger.warning("Message buffer full, dropping message")

    async def flush_buffer(self):
        """
        Send all buffered messages.
        """
        if not self.message_buffer:
            return

        logger.info(f"Flushing {len(self.message_buffer)} buffered messages")

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

    async def handle_action_command(self, message: Dict[str, Any]):
        """
        Handle action command from backend.

        Args:
            message: Message containing action details
        """
        logger.info(f"Received action command: {message.get('action')}")

        # Send acknowledgment
        await self.send_message({
            'type': 'action_ack',
            'action_id': message.get('action_id'),
            'status': 'received'
        })

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
        """
        while self.running:
            if not self.websocket or self.websocket.closed:
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    logger.info(f"Attempting reconnection (attempt {self.reconnect_attempts + 1})")

                    connected = await self.connect()

                    if connected:
                        logger.info("Reconnection successful")
                        # Start receive loop
                        asyncio.create_task(self.receive_loop())
                    else:
                        self.reconnect_attempts += 1

                        # Exponential backoff
                        delay = min(
                            self.reconnect_delay * (2 ** self.reconnect_attempts),
                            self.max_reconnect_delay
                        )
                        logger.info(f"Reconnection failed, retrying in {delay}s")
                        await asyncio.sleep(delay)
                else:
                    logger.error("Max reconnection attempts reached")
                    self.running = False
                    break

            await asyncio.sleep(1)

    async def run(self):
        """
        Run the WebSocket client.
        """
        self.running = True
        logger.info("Starting WebSocket client")

        # Register built-in handlers
        self.register_handler('action_command', self.handle_action_command)
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
