#!/usr/bin/env python3
"""
Kubernetes Metrics Collector Module

This module collects metrics from Kubernetes clusters including:
- Pod metrics (CPU, memory, status)
- Node metrics (CPU, memory, capacity)
- Cluster events
- Resource utilization

Metrics are batched and sent to the backend for analysis.
"""

import os
import sys
import time
import logging
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects metrics from Kubernetes cluster and sends to backend.
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str):
        """
        Initialize the metrics collector.

        Args:
            backend_url: URL of the backend API
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.collection_interval = int(os.getenv('COLLECTION_INTERVAL', '60'))
        self.batch_size = int(os.getenv('BATCH_SIZE', '100'))
        self.running = False
        self.metrics_buffer = []
        self.buffer_lock = threading.Lock()

        # Initialize Kubernetes clients
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig from local environment")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                raise

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects = client.CustomObjectsApi()

        logger.info(f"MetricsCollector initialized for cluster: {cluster_id}")

    def parse_cpu_value(self, cpu_string: str) -> float:
        """
        Parse CPU value from Kubernetes format.

        Args:
            cpu_string: CPU value (e.g., "100m", "1", "2.5")

        Returns:
            CPU in millicores
        """
        if not cpu_string:
            return 0.0

        cpu_string = str(cpu_string).strip()
        if cpu_string.endswith('m'):
            return float(cpu_string[:-1])
        elif cpu_string.endswith('n'):
            return float(cpu_string[:-1]) / 1000000
        else:
            return float(cpu_string) * 1000

    def parse_memory_value(self, memory_string: str) -> float:
        """
        Parse memory value from Kubernetes format.

        Args:
            memory_string: Memory value (e.g., "128Mi", "1Gi", "1024Ki")

        Returns:
            Memory in bytes
        """
        if not memory_string:
            return 0.0

        memory_string = str(memory_string).strip()
        multipliers = {
            'Ki': 1024,
            'Mi': 1024 ** 2,
            'Gi': 1024 ** 3,
            'Ti': 1024 ** 4,
            'K': 1000,
            'M': 1000 ** 2,
            'G': 1000 ** 3,
            'T': 1000 ** 4,
        }

        for suffix, multiplier in multipliers.items():
            if memory_string.endswith(suffix):
                return float(memory_string[:-len(suffix)]) * multiplier

        return float(memory_string)

    def collect_pod_metrics(self) -> List[Dict[str, Any]]:
        """
        Collect metrics for all pods in the cluster.

        Returns:
            List of pod metric dictionaries
        """
        pod_metrics = []

        try:
            # Get pod metrics from metrics.k8s.io API
            metrics = self.custom_objects.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="pods"
            )

            # Get pod details from core API
            pods = self.core_v1.list_pod_for_all_namespaces(watch=False)
            pod_details = {f"{p.metadata.namespace}/{p.metadata.name}": p for p in pods.items}

            for item in metrics.get('items', []):
                namespace = item['metadata']['namespace']
                pod_name = item['metadata']['name']
                pod_key = f"{namespace}/{pod_name}"

                pod = pod_details.get(pod_key)
                if not pod:
                    continue

                # Aggregate container metrics
                total_cpu = 0.0
                total_memory = 0.0

                for container in item.get('containers', []):
                    cpu_usage = self.parse_cpu_value(container['usage'].get('cpu', '0'))
                    memory_usage = self.parse_memory_value(container['usage'].get('memory', '0'))
                    total_cpu += cpu_usage
                    total_memory += memory_usage

                # Calculate requests and limits
                total_cpu_request = 0.0
                total_memory_request = 0.0
                total_cpu_limit = 0.0
                total_memory_limit = 0.0

                for container in pod.spec.containers:
                    if container.resources.requests:
                        total_cpu_request += self.parse_cpu_value(
                            container.resources.requests.get('cpu', '0')
                        )
                        total_memory_request += self.parse_memory_value(
                            container.resources.requests.get('memory', '0')
                        )

                    if container.resources.limits:
                        total_cpu_limit += self.parse_cpu_value(
                            container.resources.limits.get('cpu', '0')
                        )
                        total_memory_limit += self.parse_memory_value(
                            container.resources.limits.get('memory', '0')
                        )

                pod_metric = {
                    'cluster_id': self.cluster_id,
                    'namespace': namespace,
                    'pod_name': pod_name,
                    'node_name': pod.spec.node_name,
                    'phase': pod.status.phase,
                    'cpu_usage_millicores': total_cpu,
                    'memory_usage_bytes': total_memory,
                    'cpu_request_millicores': total_cpu_request,
                    'memory_request_bytes': total_memory_request,
                    'cpu_limit_millicores': total_cpu_limit,
                    'memory_limit_bytes': total_memory_limit,
                    'restart_count': sum(
                        cs.restart_count for cs in pod.status.container_statuses or []
                    ),
                    'labels': pod.metadata.labels or {},
                    'timestamp': datetime.utcnow().isoformat()
                }

                pod_metrics.append(pod_metric)

            logger.info(f"Collected metrics for {len(pod_metrics)} pods")

        except ApiException as e:
            logger.error(f"Failed to collect pod metrics: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting pod metrics: {e}", exc_info=True)

        return pod_metrics

    def collect_node_metrics(self) -> List[Dict[str, Any]]:
        """
        Collect metrics for all nodes in the cluster.

        Returns:
            List of node metric dictionaries
        """
        node_metrics = []

        try:
            # Get node metrics from metrics.k8s.io API
            metrics = self.custom_objects.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes"
            )

            # Get node details from core API
            nodes = self.core_v1.list_node(watch=False)
            node_details = {n.metadata.name: n for n in nodes.items}

            for item in metrics.get('items', []):
                node_name = item['metadata']['name']
                node = node_details.get(node_name)

                if not node:
                    continue

                cpu_usage = self.parse_cpu_value(item['usage'].get('cpu', '0'))
                memory_usage = self.parse_memory_value(item['usage'].get('memory', '0'))

                # Get node capacity
                cpu_capacity = self.parse_cpu_value(
                    node.status.capacity.get('cpu', '0')
                )
                memory_capacity = self.parse_memory_value(
                    node.status.capacity.get('memory', '0')
                )

                # Get allocatable resources
                cpu_allocatable = self.parse_cpu_value(
                    node.status.allocatable.get('cpu', '0')
                )
                memory_allocatable = self.parse_memory_value(
                    node.status.allocatable.get('memory', '0')
                )

                # Check node conditions
                ready = False
                for condition in node.status.conditions or []:
                    if condition.type == 'Ready':
                        ready = condition.status == 'True'
                        break

                node_metric = {
                    'cluster_id': self.cluster_id,
                    'node_name': node_name,
                    'cpu_usage_millicores': cpu_usage,
                    'memory_usage_bytes': memory_usage,
                    'cpu_capacity_millicores': cpu_capacity,
                    'memory_capacity_bytes': memory_capacity,
                    'cpu_allocatable_millicores': cpu_allocatable,
                    'memory_allocatable_bytes': memory_allocatable,
                    'ready': ready,
                    'unschedulable': node.spec.unschedulable or False,
                    'labels': node.metadata.labels or {},
                    'timestamp': datetime.utcnow().isoformat()
                }

                node_metrics.append(node_metric)

            logger.info(f"Collected metrics for {len(node_metrics)} nodes")

        except ApiException as e:
            logger.error(f"Failed to collect node metrics: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting node metrics: {e}", exc_info=True)

        return node_metrics

    def collect_cluster_events(self, since_seconds: int = 300) -> List[Dict[str, Any]]:
        """
        Collect recent cluster events.

        Args:
            since_seconds: Collect events from last N seconds

        Returns:
            List of event dictionaries
        """
        events = []
        cutoff_time = datetime.utcnow() - timedelta(seconds=since_seconds)

        try:
            event_list = self.core_v1.list_event_for_all_namespaces(watch=False)

            for event in event_list.items:
                event_time = event.last_timestamp or event.event_time
                if event_time and event_time.replace(tzinfo=None) > cutoff_time:
                    event_data = {
                        'cluster_id': self.cluster_id,
                        'namespace': event.metadata.namespace,
                        'name': event.metadata.name,
                        'type': event.type,
                        'reason': event.reason,
                        'message': event.message,
                        'involved_object': {
                            'kind': event.involved_object.kind,
                            'name': event.involved_object.name,
                            'namespace': event.involved_object.namespace,
                        },
                        'count': event.count or 1,
                        'timestamp': event_time.isoformat() if event_time else None
                    }
                    events.append(event_data)

            logger.info(f"Collected {len(events)} recent cluster events")

        except ApiException as e:
            logger.error(f"Failed to collect cluster events: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting cluster events: {e}", exc_info=True)

        return events

    def add_to_buffer(self, metrics: List[Dict[str, Any]]):
        """
        Add metrics to the buffer for batch sending.

        Args:
            metrics: List of metric dictionaries
        """
        with self.buffer_lock:
            self.metrics_buffer.extend(metrics)

    def send_metrics_to_backend(self, metrics: List[Dict[str, Any]]) -> bool:
        """
        Send metrics to the backend API.

        Args:
            metrics: List of metric dictionaries

        Returns:
            True if successful, False otherwise
        """
        if not metrics:
            return True

        url = f"{self.backend_url}/api/v1/metrics/batch"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Successfully sent {len(metrics)} metrics to backend")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send metrics to backend: {e}")
            return False

    def flush_buffer(self):
        """
        Flush the metrics buffer by sending all buffered metrics.
        """
        with self.buffer_lock:
            if not self.metrics_buffer:
                return

            metrics_to_send = self.metrics_buffer[:self.batch_size]
            if self.send_metrics_to_backend(metrics_to_send):
                self.metrics_buffer = self.metrics_buffer[self.batch_size:]
            else:
                logger.warning("Failed to send metrics, keeping in buffer")

    def collect_and_send(self):
        """
        Main collection loop: collect all metrics and send to backend.
        """
        logger.info("Starting metrics collection cycle")

        # Collect all metrics
        pod_metrics = self.collect_pod_metrics()
        node_metrics = self.collect_node_metrics()
        events = self.collect_cluster_events()

        # Add to buffer
        all_metrics = []

        for metric in pod_metrics:
            metric['metric_type'] = 'pod'
            all_metrics.append(metric)

        for metric in node_metrics:
            metric['metric_type'] = 'node'
            all_metrics.append(metric)

        for event in events:
            event['metric_type'] = 'event'
            all_metrics.append(event)

        self.add_to_buffer(all_metrics)

        # Flush buffer
        self.flush_buffer()

        logger.info(f"Collection cycle complete. Buffer size: {len(self.metrics_buffer)}")

    def run(self):
        """
        Run the metrics collector in a loop.
        """
        self.running = True
        logger.info(f"Starting metrics collector with {self.collection_interval}s interval")

        while self.running:
            try:
                self.collect_and_send()
            except Exception as e:
                logger.error(f"Error in collection cycle: {e}", exc_info=True)

            # Wait for next collection interval
            time.sleep(self.collection_interval)

        logger.info("Metrics collector stopped")

    def stop(self):
        """
        Stop the metrics collector.
        """
        logger.info("Stopping metrics collector...")
        self.running = False

        # Final flush
        self.flush_buffer()


if __name__ == '__main__':
    # Test the collector
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
    api_key = os.getenv('API_KEY', 'test-key')
    cluster_id = os.getenv('CLUSTER_ID', 'test-cluster')

    collector = MetricsCollector(backend_url, api_key, cluster_id)

    try:
        collector.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        collector.stop()
        sys.exit(0)
