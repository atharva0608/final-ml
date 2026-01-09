#!/usr/bin/env python3
"""
Heartbeat and Health Monitoring Module

This module provides:
- HTTP health check endpoints (/healthz, /readyz)
- Periodic heartbeat to backend
- Agent health metrics collection
- System resource monitoring
"""

import os
import sys
import time
import logging
import threading
import psutil
from typing import Dict, Any
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for health check endpoints.
    """

    def log_message(self, format, *args):
        """Override to use logger instead of stderr."""
        logger.debug(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/healthz':
            self.handle_healthz()
        elif self.path == '/readyz':
            self.handle_readyz()
        elif self.path == '/metrics':
            self.handle_metrics()
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

    def handle_healthz(self):
        """Handle liveness probe."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat()
        }
        self.wfile.write(str(response).encode('utf-8'))

    def handle_readyz(self):
        """Handle readiness probe."""
        # Check if the server is ready to accept traffic
        server = self.server
        if hasattr(server, 'ready') and server.ready:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                'status': 'ready',
                'timestamp': datetime.utcnow().isoformat()
            }
            self.wfile.write(str(response).encode('utf-8'))
        else:
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                'status': 'not ready',
                'timestamp': datetime.utcnow().isoformat()
            }
            self.wfile.write(str(response).encode('utf-8'))

    def handle_metrics(self):
        """Handle metrics endpoint."""
        server = self.server
        metrics = {}

        if hasattr(server, 'get_metrics'):
            metrics = server.get_metrics()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        import json
        self.wfile.write(json.dumps(metrics).encode('utf-8'))


class HealthServer(HTTPServer):
    """
    HTTP server with custom attributes for health checks.
    """

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.ready = False
        self.metrics_callback = None

    def set_ready(self, ready: bool):
        """Set readiness status."""
        self.ready = ready
        logger.info(f"Server readiness set to: {ready}")

    def set_metrics_callback(self, callback):
        """Set callback for metrics collection."""
        self.metrics_callback = callback

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        if self.metrics_callback:
            return self.metrics_callback()
        return {}


class HeartbeatSender:
    """
    Sends periodic heartbeats to backend and manages health checks.
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str,
                 agent_id: str, heartbeat_interval: int = 30):
        """
        Initialize the heartbeat sender.

        Args:
            backend_url: URL of the backend API
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
            agent_id: Unique identifier for this agent
            heartbeat_interval: Interval in seconds between heartbeats
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.agent_id = agent_id
        self.heartbeat_interval = heartbeat_interval
        self.running = False
        self.health_server = None
        self.server_thread = None

        # Component health status
        self.component_health = {
            'collector': False,
            'actuator': False,
            'websocket': False
        }

        logger.info(f"HeartbeatSender initialized for agent: {agent_id}")

    def start_health_server(self, port: int = 8080):
        """
        Start the HTTP health check server.

        Args:
            port: Port to listen on
        """
        try:
            self.health_server = HealthServer(('0.0.0.0', port), HealthCheckHandler)
            self.health_server.set_metrics_callback(self.collect_agent_metrics)

            self.server_thread = threading.Thread(
                target=self.health_server.serve_forever,
                daemon=True
            )
            self.server_thread.start()

            logger.info(f"Health check server started on port {port}")

        except Exception as e:
            logger.error(f"Failed to start health server: {e}", exc_info=True)
            raise

    def stop_health_server(self):
        """Stop the HTTP health check server."""
        if self.health_server:
            logger.info("Stopping health check server")
            self.health_server.shutdown()
            self.health_server.server_close()

            if self.server_thread:
                self.server_thread.join(timeout=5)

    def set_component_health(self, component: str, healthy: bool):
        """
        Set health status for a component.

        Args:
            component: Component name (collector, actuator, websocket)
            healthy: Health status
        """
        if component in self.component_health:
            self.component_health[component] = healthy
            logger.info(f"Component {component} health set to: {healthy}")

            # Update readiness based on component health
            self.update_readiness()

    def update_readiness(self):
        """Update server readiness based on component health."""
        # Agent is ready if at least collector is healthy
        ready = self.component_health.get('collector', False)

        if self.health_server:
            self.health_server.set_ready(ready)

    def collect_agent_metrics(self) -> Dict[str, Any]:
        """
        Collect agent system metrics.

        Returns:
            Dictionary of agent metrics
        """
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_total = memory.total
            memory_used = memory.used
            memory_percent = memory.percent

            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_total = disk.total
            disk_used = disk.used
            disk_percent = disk.percent

            # Network metrics
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv

            # Process metrics
            process = psutil.Process()
            process_memory = process.memory_info().rss
            process_cpu = process.cpu_percent(interval=0.1)

            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count
                },
                'memory': {
                    'total': memory_total,
                    'used': memory_used,
                    'percent': memory_percent
                },
                'disk': {
                    'total': disk_total,
                    'used': disk_used,
                    'percent': disk_percent
                },
                'network': {
                    'bytes_sent': bytes_sent,
                    'bytes_received': bytes_recv
                },
                'process': {
                    'memory_bytes': process_memory,
                    'cpu_percent': process_cpu
                },
                'components': self.component_health
            }

            return metrics

        except Exception as e:
            logger.error(f"Error collecting agent metrics: {e}", exc_info=True)
            return {}

    def send_heartbeat(self) -> bool:
        """
        Send heartbeat to backend.

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.backend_url}/api/v1/agents/heartbeat"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        # Collect metrics
        metrics = self.collect_agent_metrics()

        payload = {
            'cluster_id': self.cluster_id,
            'agent_id': self.agent_id,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'healthy',
            'metrics': metrics,
            'components': self.component_health
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.debug(f"Heartbeat sent successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def run(self):
        """
        Run the heartbeat sender in a loop.
        """
        self.running = True
        logger.info(f"Starting heartbeat sender with {self.heartbeat_interval}s interval")

        # Start health check server
        self.start_health_server()

        while self.running:
            try:
                self.send_heartbeat()
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)

            # Wait for next heartbeat
            time.sleep(self.heartbeat_interval)

        logger.info("Heartbeat sender stopped")

    def stop(self):
        """
        Stop the heartbeat sender.
        """
        logger.info("Stopping heartbeat sender...")
        self.running = False

        # Send final heartbeat
        try:
            url = f"{self.backend_url}/api/v1/agents/heartbeat"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'cluster_id': self.cluster_id,
                'agent_id': self.agent_id,
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'stopping'
            }
            requests.post(url, json=payload, headers=headers, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send final heartbeat: {e}")

        # Stop health server
        self.stop_health_server()


if __name__ == '__main__':
    # Test the heartbeat sender
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
    api_key = os.getenv('API_KEY', 'test-key')
    cluster_id = os.getenv('CLUSTER_ID', 'test-cluster')
    agent_id = os.getenv('AGENT_ID', 'test-agent')

    heartbeat = HeartbeatSender(backend_url, api_key, cluster_id, agent_id)

    # Simulate component health
    heartbeat.set_component_health('collector', True)
    heartbeat.set_component_health('actuator', True)

    try:
        heartbeat.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        heartbeat.stop()
        sys.exit(0)
