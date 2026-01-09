#!/usr/bin/env python3
"""
Kubernetes Agent Main Module

This is the main entry point for the Kubernetes agent. It:
- Initializes all components (collector, actuator, heartbeat, websocket)
- Registers the agent with the backend
- Manages component lifecycle
- Handles graceful shutdown
- Monitors component health
"""

import os
import sys
import time
import signal
import logging
import threading
import asyncio
from typing import Optional
from datetime import datetime
import requests

# Import agent modules
from collector import MetricsCollector
from actuator import ActionActuator
from heartbeat import HeartbeatSender
from websocket_client import WebSocketClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Agent:
    """
    Main agent class that coordinates all components.
    """

    def __init__(self):
        """
        Initialize the agent with configuration from environment variables.
        """
        # Backend configuration
        self.backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
        self.backend_ws_url = os.getenv('BACKEND_WS_URL', 'ws://localhost:8000/ws')
        self.api_key = os.getenv('API_KEY')
        self.secret_key = os.getenv('SECRET_KEY')

        # Cluster identification
        self.cluster_id = os.getenv('CLUSTER_ID')
        self.agent_id = os.getenv('AGENT_ID', self._generate_agent_id())

        # Validate required configuration
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")
        if not self.secret_key:
            raise ValueError("SECRET_KEY environment variable is required")
        if not self.cluster_id:
            raise ValueError("CLUSTER_ID environment variable is required")

        # Components
        self.collector = None
        self.actuator = None
        self.heartbeat = None
        self.websocket_client = None

        # Threads
        self.collector_thread = None
        self.actuator_thread = None
        self.heartbeat_thread = None
        self.websocket_thread = None

        # State
        self.running = False
        self.shutdown_event = threading.Event()

        logger.info(f"Agent initialized: cluster={self.cluster_id}, agent={self.agent_id}")

    def _generate_agent_id(self) -> str:
        """
        Generate a unique agent ID.

        Returns:
            Generated agent ID
        """
        import socket
        import uuid

        hostname = socket.gethostname()
        unique_id = str(uuid.uuid4())[:8]

        return f"{hostname}-{unique_id}"

    def register_with_backend(self) -> bool:
        """
        Register the agent with the backend.

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.backend_url}/api/v1/agents/register"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'agent_id': self.agent_id,
            'timestamp': datetime.utcnow().isoformat(),
            'capabilities': [
                'metrics_collection',
                'action_execution',
                'websocket_communication'
            ],
            'version': '1.0.0'
        }

        try:
            logger.info("Registering agent with backend...")
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"Agent registered successfully: {data}")

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register with backend: {e}")
            return False

    def deregister_from_backend(self) -> bool:
        """
        Deregister the agent from the backend.

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.backend_url}/api/v1/agents/deregister"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'agent_id': self.agent_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        try:
            logger.info("Deregistering agent from backend...")
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            logger.info("Agent deregistered successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to deregister from backend: {e}")
            return False

    def initialize_components(self):
        """
        Initialize all agent components.
        """
        logger.info("Initializing components...")

        # Initialize metrics collector
        self.collector = MetricsCollector(
            backend_url=self.backend_url,
            api_key=self.api_key,
            cluster_id=self.cluster_id
        )
        logger.info("Metrics collector initialized")

        # Initialize action actuator
        self.actuator = ActionActuator(
            backend_url=self.backend_url,
            api_key=self.api_key,
            cluster_id=self.cluster_id,
            secret_key=self.secret_key
        )
        logger.info("Action actuator initialized")

        # Initialize heartbeat sender
        self.heartbeat = HeartbeatSender(
            backend_url=self.backend_url,
            api_key=self.api_key,
            cluster_id=self.cluster_id,
            agent_id=self.agent_id
        )
        logger.info("Heartbeat sender initialized")

        # Initialize WebSocket client
        self.websocket_client = WebSocketClient(
            backend_ws_url=self.backend_ws_url,
            api_key=self.api_key,
            cluster_id=self.cluster_id,
            agent_id=self.agent_id
        )
        logger.info("WebSocket client initialized")

        logger.info("All components initialized successfully")

    def start_components(self):
        """
        Start all agent components in separate threads.
        """
        logger.info("Starting components...")

        # Start metrics collector
        self.collector_thread = threading.Thread(
            target=self.collector.run,
            name="MetricsCollector",
            daemon=True
        )
        self.collector_thread.start()
        logger.info("Metrics collector started")

        # Update health status
        if self.heartbeat:
            self.heartbeat.set_component_health('collector', True)

        # Start action actuator
        self.actuator_thread = threading.Thread(
            target=self.actuator.run,
            name="ActionActuator",
            daemon=True
        )
        self.actuator_thread.start()
        logger.info("Action actuator started")

        # Update health status
        if self.heartbeat:
            self.heartbeat.set_component_health('actuator', True)

        # Start heartbeat sender
        self.heartbeat_thread = threading.Thread(
            target=self.heartbeat.run,
            name="HeartbeatSender",
            daemon=True
        )
        self.heartbeat_thread.start()
        logger.info("Heartbeat sender started")

        # Start WebSocket client
        self.websocket_thread = threading.Thread(
            target=self._run_websocket_client,
            name="WebSocketClient",
            daemon=True
        )
        self.websocket_thread.start()
        logger.info("WebSocket client started")

        # Update health status
        if self.heartbeat:
            self.heartbeat.set_component_health('websocket', True)

        logger.info("All components started successfully")

    def _run_websocket_client(self):
        """
        Run the WebSocket client in a thread.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.websocket_client.run())
        except Exception as e:
            logger.error(f"WebSocket client error: {e}", exc_info=True)
        finally:
            loop.close()

    def stop_components(self):
        """
        Stop all agent components gracefully.
        """
        logger.info("Stopping components...")

        # Update health status
        if self.heartbeat:
            self.heartbeat.set_component_health('collector', False)
            self.heartbeat.set_component_health('actuator', False)
            self.heartbeat.set_component_health('websocket', False)

        # Stop metrics collector
        if self.collector:
            self.collector.stop()
            logger.info("Metrics collector stopped")

        # Stop action actuator
        if self.actuator:
            self.actuator.stop()
            logger.info("Action actuator stopped")

        # Stop WebSocket client
        if self.websocket_client:
            # Need to run async stop in the event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_client.stop())
                loop.close()
            except Exception as e:
                logger.error(f"Error stopping WebSocket client: {e}")
            logger.info("WebSocket client stopped")

        # Stop heartbeat sender (last, so we can report shutdown)
        if self.heartbeat:
            self.heartbeat.stop()
            logger.info("Heartbeat sender stopped")

        # Wait for threads to finish
        timeout = 10
        for thread in [self.collector_thread, self.actuator_thread,
                      self.websocket_thread, self.heartbeat_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=timeout)

        logger.info("All components stopped")

    def handle_shutdown_signal(self, signum, frame):
        """
        Handle shutdown signals (SIGTERM, SIGINT).

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal, initiating graceful shutdown...")

        self.shutdown_event.set()
        self.running = False

    def monitor_components(self):
        """
        Monitor component health and restart if necessary.
        """
        while self.running and not self.shutdown_event.is_set():
            # Check collector thread
            if self.collector_thread and not self.collector_thread.is_alive():
                logger.error("Metrics collector thread died, restarting...")
                self.collector_thread = threading.Thread(
                    target=self.collector.run,
                    name="MetricsCollector",
                    daemon=True
                )
                self.collector_thread.start()

            # Check actuator thread
            if self.actuator_thread and not self.actuator_thread.is_alive():
                logger.error("Action actuator thread died, restarting...")
                self.actuator_thread = threading.Thread(
                    target=self.actuator.run,
                    name="ActionActuator",
                    daemon=True
                )
                self.actuator_thread.start()

            # Check heartbeat thread
            if self.heartbeat_thread and not self.heartbeat_thread.is_alive():
                logger.error("Heartbeat sender thread died, restarting...")
                self.heartbeat_thread = threading.Thread(
                    target=self.heartbeat.run,
                    name="HeartbeatSender",
                    daemon=True
                )
                self.heartbeat_thread.start()

            # Check WebSocket thread
            if self.websocket_thread and not self.websocket_thread.is_alive():
                logger.error("WebSocket client thread died, restarting...")
                self.websocket_thread = threading.Thread(
                    target=self._run_websocket_client,
                    name="WebSocketClient",
                    daemon=True
                )
                self.websocket_thread.start()

            # Sleep before next check
            time.sleep(30)

    def run(self):
        """
        Main run method for the agent.
        """
        logger.info("Starting Kubernetes Agent...")

        # Register signal handlers
        signal.signal(signal.SIGTERM, self.handle_shutdown_signal)
        signal.signal(signal.SIGINT, self.handle_shutdown_signal)

        # Register with backend
        if not self.register_with_backend():
            logger.error("Failed to register with backend, exiting...")
            return 1

        try:
            # Initialize components
            self.initialize_components()

            # Start components
            self.start_components()

            # Set running flag
            self.running = True

            logger.info("Agent is running. Press Ctrl+C to stop.")

            # Monitor components
            self.monitor_components()

        except Exception as e:
            logger.error(f"Fatal error in agent: {e}", exc_info=True)
            return 1

        finally:
            # Stop components
            self.stop_components()

            # Deregister from backend
            self.deregister_from_backend()

            logger.info("Agent shutdown complete")

        return 0


def main():
    """
    Main entry point.
    """
    try:
        agent = Agent()
        exit_code = agent.run()
        sys.exit(exit_code)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
