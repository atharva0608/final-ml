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
from typing import Optional, Dict
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Import agent modules
from collector import MetricsCollector
from actuator import ActionActuator
from heartbeat import HeartbeatSender
from websocket_client import WebSocketClient
from poller import SpotPoller
from pod_metrics_collector import PodMetricsCollector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── Lightweight /healthz HTTP server for K8s probes & Docker HEALTHCHECK ──
class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal handler: GET /healthz → 200, everything else → 404."""
    agent_ref = None  # set by Agent after construction

    def do_GET(self):
        if self.path == '/healthz':
            ok = self.agent_ref and getattr(self.agent_ref, 'running', False)
            status = 200 if ok else 503
            body = b'{"status":"ok"}' if ok else b'{"status":"starting"}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # silence per-request logs


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

        # Track the original URL for discover-url fallback
        self._initial_backend_url = self.backend_url
        self._last_url_refresh = 0  # epoch timestamp

        # Cluster identification
        self.cluster_id = os.getenv('CLUSTER_ID')
        self.agent_id = os.getenv('AGENT_ID', self._generate_agent_id())

        # Validate required configuration
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")
        # SECRET_KEY is optional; generate a default if not provided
        if not self.secret_key:
            self.secret_key = self._generate_agent_id()  # Use agent_id as fallback secret
            logger.warning("SECRET_KEY not provided, using auto-generated value")
        if not self.cluster_id:
            raise ValueError("CLUSTER_ID environment variable is required")

        # Components
        self.collector = None
        self.actuator = None
        self.heartbeat = None
        self.websocket_client = None
        self.spot_poller = None
        self.pod_metrics_collector = None

        # Threads
        self.collector_thread = None
        self.actuator_thread = None
        self.heartbeat_thread = None
        self.websocket_thread = None
        self.spot_poller_thread = None
        self.pod_metrics_thread = None

        # State
        self.running = False
        self.shutdown_event = threading.Event()
        self._health_server = None

        # Task-1.8: Thread restart counters and backoff state (Issue #9)
        # Prevents runaway restarts: max 5 attempts per component, then DEAD.
        self._restart_counts: Dict[str, int] = {}
        self._restart_backoffs: Dict[str, float] = {}
        _components = ['collector', 'actuator', 'heartbeat', 'websocket', 'spot_poller', 'pod_metrics']
        for _c in _components:
            self._restart_counts[_c] = 0
            self._restart_backoffs[_c] = 0.0

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

    # ── Dynamic backend URL discovery ──────────────────────────────────────
    def _refresh_backend_url(self) -> bool:
        """
        Call the backend's /api/v1/agents/discover-url endpoint to get the
        current public URL.  This handles tunnel URL rotation (ngrok,
        Cloudflare Tunnel, etc.) without needing to restart pods or update
        ConfigMaps.

        Returns True if the URL was updated, False otherwise.
        """
        url = f"{self.backend_url}/api/v1/agents/discover-url"
        try:
            resp = requests.get(url, timeout=10, headers={'ngrok-skip-browser-warning': 'true'})
            if resp.status_code == 200:
                data = resp.json()
                new_url = data.get("backend_url", "").rstrip("/")
                if new_url and new_url != self.backend_url:
                    return self._update_backend_url(new_url)
                self._last_url_refresh = time.time()
                return False
        except Exception as e:
            logger.debug(f"discover-url failed on current URL: {e}")

        # If current URL failed and it's different from the initial, try initial too
        if self._initial_backend_url != self.backend_url:
            try:
                url = f"{self._initial_backend_url}/api/v1/agents/discover-url"
                resp = requests.get(url, timeout=10, headers={'ngrok-skip-browser-warning': 'true'})
                if resp.status_code == 200:
                    data = resp.json()
                    new_url = data.get("backend_url", "").rstrip("/")
                    if new_url:
                        return self._update_backend_url(new_url)
            except Exception as e:
                logger.debug(f"discover-url failed on initial URL too: {e}")

        return False

    def _update_backend_url(self, new_url: str) -> bool:
        """
        Update the backend URL across the agent and all running components.
        Called when the discover-url endpoint or registration response
        reports a different URL than the one we're currently using.
        """
        old_url = self.backend_url
        self.backend_url = new_url
        new_ws = new_url.replace("https://", "wss://").replace("http://", "ws://")
        self.backend_ws_url = f"{new_ws}/ws/cluster/{self.cluster_id}"
        self._last_url_refresh = time.time()

        logger.info(f"[URL-REFRESH] Backend URL changed: {old_url} → {new_url}")

        # Propagate to running components
        if self.collector:
            self.collector.backend_url = new_url
        if self.actuator:
            self.actuator.backend_url = new_url
        if self.heartbeat:
            self.heartbeat.backend_url = new_url
        if self.pod_metrics_collector:
            self.pod_metrics_collector.backend_url = new_url

        # WebSocket client needs reconnect with new URL
        if self.websocket_client:
            self.websocket_client.backend_ws_url = self.backend_ws_url
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_client.stop())
                loop.close()
            except Exception:
                pass

        return True
    # ────────────────────────────────────────────────────────────────────────

    def register_with_backend(self) -> bool:
        """
        Register the agent with the backend.

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.backend_url}/api/v1/agents/register"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

        # Get cluster metadata from environment or defaults
        cluster_name = os.getenv('CLUSTER_NAME', f'k8s-cluster-{self.cluster_id[:8]}')
        region = os.getenv('AWS_REGION', os.getenv('CLUSTER_REGION', 'us-east-1'))

        payload = {
            'cluster_id': self.cluster_id,
            'agent_id': self.agent_id,
            'cluster_name': cluster_name,
            'region': region,
            'timestamp': datetime.utcnow().isoformat(),
            'capabilities': [
                'metrics_collection',
                'action_execution',
                'websocket_communication'
            ],
            'version': '1.1.6'
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

            # If the backend returned a different URL, update dynamically
            returned_url = (data.get("backend_url") or "").rstrip("/")
            if returned_url and returned_url != self.backend_url:
                self._update_backend_url(returned_url)

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register with backend: {e}")
            # Try to discover the new URL — the tunnel may have rotated
            self._refresh_backend_url()
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
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
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
        # Wire actuator into WebSocket client so it can execute backend commands
        self.websocket_client.set_actuator(self.actuator)
        logger.info("WebSocket client initialized (actuator wired)")

        # Initialize Spot Poller (Runtime Safety)
        self.spot_poller = SpotPoller(
            actuator=self.actuator,
            interval=5
        )
        logger.info("Spot Termination Poller initialized")

        # Initialize Pod Metrics Collector (Right-Sizing)
        self.pod_metrics_collector = PodMetricsCollector(
            backend_url=self.backend_url,
            api_key=self.api_key,
            cluster_id=self.cluster_id
        )
        logger.info("Pod Metrics Collector initialized")

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

        # Start Spot Poller
        self.spot_poller_thread = threading.Thread(
            target=self.spot_poller.run,
            name="SpotPoller",
            daemon=True
        )
        self.spot_poller_thread.start()
        logger.info("Spot Termination Poller started")

        # Start Pod Metrics Collector
        self.pod_metrics_thread = threading.Thread(
            target=self.pod_metrics_collector.run,
            name="PodMetricsCollector",
            daemon=True
        )
        self.pod_metrics_thread.start()
        logger.info("Pod Metrics Collector started")

        # Update health status
        if self.heartbeat:
            self.heartbeat.set_component_health('websocket', True)
            self.heartbeat.set_component_health('pod_metrics', True)

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

        # Stop Spot Poller
        if self.spot_poller:
            self.spot_poller.stop()
            logger.info("Spot Termination Poller stopped")

        # Stop Pod Metrics Collector
        if self.pod_metrics_collector:
            self.pod_metrics_collector.stop()
            logger.info("Pod Metrics Collector stopped")

        # Stop heartbeat sender (last, so we can report shutdown)
        if self.heartbeat:
            self.heartbeat.stop()
            logger.info("Heartbeat sender stopped")

        # Wait for threads to finish
        timeout = 10
        for thread in [self.collector_thread, self.actuator_thread,
                      self.websocket_thread, self.heartbeat_thread,
                      self.spot_poller_thread, self.pod_metrics_thread]:
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

    def _restart_thread(self, name: str, target, thread_attr: str) -> None:
        """
        Task-1.8 (Issue #9): Restart a dead component thread with exponential backoff.

        Uses a sliding window: restart counter resets after 5 minutes of
        stable uptime.  This prevents permanent DEAD state from transient
        failures accumulating across long agent sessions (e.g. ngrok tunnel
        rotations, brief network blips).
        """
        MAX_RESTARTS = 10
        now = time.time()

        # Reset counter if the component ran for >5 min since last restart
        last_restart_time = self._restart_backoffs.get(name, 0.0)
        if last_restart_time and (now - last_restart_time) > 300:
            self._restart_counts[name] = 0

        count = self._restart_counts.get(name, 0) + 1
        self._restart_counts[name] = count
        self._restart_backoffs[name] = now

        if count > MAX_RESTARTS:
            logger.critical(
                f"[monitor] Component '{name}' has crashed {count} times in quick "
                f"succession — marking DEAD. Manual intervention required."
            )
            return

        backoff = min(2 ** count, 60)  # 2s, 4s, 8s, 16s, 32s, then capped at 60s
        logger.error(
            f"[monitor] Component '{name}' thread died (attempt {count}/{MAX_RESTARTS}). "
            f"Restarting in {backoff}s..."
        )
        time.sleep(backoff)

        new_thread = threading.Thread(target=target, name=name.title().replace('_', ''), daemon=True)
        new_thread.start()
        setattr(self, thread_attr, new_thread)
        logger.info(f"[monitor] Component '{name}' restarted (attempt {count}).")

    def monitor_components(self):
        """
        Monitor component health and restart if necessary.
        """
        while self.running and not self.shutdown_event.is_set():
            if self.collector_thread and not self.collector_thread.is_alive():
                self._restart_thread('collector', self.collector.run, 'collector_thread')

            if self.actuator_thread and not self.actuator_thread.is_alive():
                self._restart_thread('actuator', self.actuator.run, 'actuator_thread')

            if self.heartbeat_thread and not self.heartbeat_thread.is_alive():
                self._restart_thread('heartbeat', self.heartbeat.run, 'heartbeat_thread')

            if self.websocket_thread and not self.websocket_thread.is_alive():
                self._restart_thread('websocket', self._run_websocket_client, 'websocket_thread')

            if self.spot_poller_thread and not self.spot_poller_thread.is_alive():
                self._restart_thread('spot_poller', self.spot_poller.run, 'spot_poller_thread')

            if self.pod_metrics_thread and not self.pod_metrics_thread.is_alive():
                self._restart_thread('pod_metrics', self.pod_metrics_collector.run, 'pod_metrics_thread')

            # Periodic backend URL refresh (every 5 minutes)
            if time.time() - self._last_url_refresh > 300:
                try:
                    self._refresh_backend_url()
                except Exception as e:
                    logger.debug(f"Periodic URL refresh failed: {e}")

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

        # Start /healthz HTTP server (port 8080) for K8s probes
        try:
            _HealthHandler.agent_ref = self
            self._health_server = HTTPServer(('0.0.0.0', 8080), _HealthHandler)
            _ht = threading.Thread(target=self._health_server.serve_forever, daemon=True)
            _ht.start()
            logger.info("Health server started on :8080/healthz")
        except Exception as _he:
            logger.warning(f"Health server failed to start (non-fatal): {_he}")

        # Register with backend (retry with backoff — never exit on transient failure)
        _reg_attempt = 0
        _reg_max_backoff = 120  # cap at 2 minutes between retries
        while True:
            if self.register_with_backend():
                break
            _reg_attempt += 1
            _backoff = min(_reg_max_backoff, 5 * (2 ** min(_reg_attempt - 1, 5)))
            logger.warning(
                f"Registration attempt {_reg_attempt} failed. "
                f"Retrying in {_backoff}s... (backend may be restarting or URL may have changed)"
            )
            time.sleep(_backoff)
            if self.shutdown_event.is_set():
                logger.info("Shutdown requested during registration retry, exiting...")
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
            # Stop health server
            if self._health_server:
                self._health_server.shutdown()

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
