#!/usr/bin/env python3
"""
Pod Metrics Collector Module for Right-Sizing

Collects pod-level resource usage metrics for the right-sizing engine.
Sends metrics to /api/v1/pod-metrics/batch every 5 minutes.

Key features:
- Extracts controller owner references (Deployment, StatefulSet, etc.)
- Collects CPU/memory usage from metrics.k8s.io API
- Collects CPU/memory requests/limits from pod specs
- Batches metrics by node for efficient submission
- Handles DaemonSet-specific logic (only sends pods on local node)
"""

import os
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class PodMetricsCollector:
    """
    Collects pod-level metrics for right-sizing analysis.
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str):
        """
        Initialize the pod metrics collector.

        Args:
            backend_url: URL of the backend API
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.node_name = os.getenv('NODE_NAME')  # DaemonSet provides this
        self.collection_interval = int(os.getenv('POD_METRICS_INTERVAL', '300'))  # 5 minutes default
        self.running = False

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
        self.custom_objects = client.CustomObjectsApi()

        logger.info(f"PodMetricsCollector initialized for cluster: {cluster_id}, node: {self.node_name}")

    def parse_cpu_value(self, cpu_string: str) -> int:
        """
        Parse CPU value from Kubernetes format to millicores.

        Args:
            cpu_string: CPU value (e.g., "100m", "1", "2.5")

        Returns:
            CPU in millicores (int)
        """
        if not cpu_string:
            return 0

        cpu_string = str(cpu_string).strip()
        if cpu_string.endswith('m'):
            return int(float(cpu_string[:-1]))
        elif cpu_string.endswith('n'):
            return int(float(cpu_string[:-1]) / 1000000)
        else:
            return int(float(cpu_string) * 1000)

    def parse_memory_value(self, memory_string: str) -> int:
        """
        Parse memory value from Kubernetes format to bytes.

        Args:
            memory_string: Memory value (e.g., "128Mi", "1Gi", "1024Ki")

        Returns:
            Memory in bytes (int)
        """
        if not memory_string:
            return 0

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
                return int(float(memory_string[:-len(suffix)]) * multiplier)

        return int(float(memory_string))

    def get_controller_info(self, pod) -> tuple:
        """
        Extract controller information from pod owner references.

        Args:
            pod: Kubernetes pod object

        Returns:
            Tuple of (controller_kind, controller_name)
        """
        if not pod.metadata.owner_references:
            return None, None

        # Get first owner reference (usually the direct controller)
        owner = pod.metadata.owner_references[0]
        controller_kind = owner.kind
        controller_name = owner.name

        # If owner is a ReplicaSet, try to find parent Deployment
        if controller_kind == 'ReplicaSet':
            try:
                apps_v1 = client.AppsV1Api()
                rs = apps_v1.read_namespaced_replica_set(
                    controller_name,
                    pod.metadata.namespace
                )
                if rs.metadata.owner_references:
                    parent_owner = rs.metadata.owner_references[0]
                    controller_kind = parent_owner.kind
                    controller_name = parent_owner.name
            except Exception as e:
                logger.debug(f"Could not resolve ReplicaSet parent: {e}")

        return controller_kind, controller_name

    def collect_pod_metrics(self) -> List[Dict[str, Any]]:
        """
        Collect pod-level metrics for right-sizing analysis.

        Returns:
            List of pod metric dictionaries ready for API submission
        """
        pod_metrics = []

        try:
            # Get pod metrics from metrics.k8s.io API
            metrics = self.custom_objects.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="pods"
            )

            # Get all pod details from core API
            pods_list = self.core_v1.list_pod_for_all_namespaces(watch=False)
            pod_details = {f"{p.metadata.namespace}/{p.metadata.name}": p for p in pods_list.items}

            for item in metrics.get('items', []):
                namespace = item['metadata']['namespace']
                pod_name = item['metadata']['name']
                pod_key = f"{namespace}/{pod_name}"

                pod = pod_details.get(pod_key)
                if not pod:
                    continue

                # Skip system namespaces (optional - can be configured)
                if namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                # If running as DaemonSet, only collect metrics for pods on this node
                if self.node_name and pod.spec.node_name != self.node_name:
                    continue

                # Get controller information
                controller_kind, controller_name = self.get_controller_info(pod)

                # Aggregate container metrics
                total_cpu_usage = 0
                total_memory_usage = 0
                container_count = 0

                for container in item.get('containers', []):
                    cpu_usage = self.parse_cpu_value(container['usage'].get('cpu', '0'))
                    memory_usage = self.parse_memory_value(container['usage'].get('memory', '0'))
                    total_cpu_usage += cpu_usage
                    total_memory_usage += memory_usage
                    container_count += 1

                # Calculate requests and limits from pod spec
                total_cpu_request = 0
                total_memory_request = 0
                total_cpu_limit = 0
                total_memory_limit = 0

                for container in pod.spec.containers:
                    if container.resources and container.resources.requests:
                        total_cpu_request += self.parse_cpu_value(
                            container.resources.requests.get('cpu', '0')
                        )
                        total_memory_request += self.parse_memory_value(
                            container.resources.requests.get('memory', '0')
                        )

                    if container.resources and container.resources.limits:
                        total_cpu_limit += self.parse_cpu_value(
                            container.resources.limits.get('cpu', '0')
                        )
                        total_memory_limit += self.parse_memory_value(
                            container.resources.limits.get('memory', '0')
                        )

                # Build metric object matching PodMetricCreate schema
                pod_metric = {
                    'namespace': namespace,
                    'pod_name': pod_name,
                    'node_name': pod.spec.node_name or 'unknown',
                    'controller_kind': controller_kind,
                    'controller_name': controller_name,
                    'cpu_usage_millicores': total_cpu_usage,
                    'cpu_request_millicores': total_cpu_request if total_cpu_request > 0 else None,
                    'cpu_limit_millicores': total_cpu_limit if total_cpu_limit > 0 else None,
                    'memory_usage_bytes': total_memory_usage,
                    'memory_request_bytes': total_memory_request if total_memory_request > 0 else None,
                    'memory_limit_bytes': total_memory_limit if total_memory_limit > 0 else None,
                    'container_count': container_count,
                    'metadata': {
                        'labels': pod.metadata.labels or {},
                        'phase': pod.status.phase,
                        'qos_class': pod.status.qos_class
                    }
                }

                pod_metrics.append(pod_metric)

            logger.info(f"Collected metrics for {len(pod_metrics)} pods on node {self.node_name}")

        except ApiException as e:
            logger.error(f"Failed to collect pod metrics from metrics API: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting pod metrics: {e}", exc_info=True)

        return pod_metrics

    def send_pod_metrics_batch(self, metrics: List[Dict[str, Any]]) -> bool:
        """
        Send pod metrics batch to backend.

        Args:
            metrics: List of pod metric dictionaries

        Returns:
            True if successful, False otherwise
        """
        if not metrics:
            logger.info("No pod metrics to send")
            return True

        url = f"{self.backend_url}/api/v1/pod-metrics/batch"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'node_name': self.node_name or 'unknown',
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': metrics
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"Successfully sent {result.get('metrics_inserted', 0)} pod metrics to backend")

            if result.get('errors'):
                logger.warning(f"Some errors occurred: {result['errors']}")

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send pod metrics to backend: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return False

    def collect_and_send(self):
        """
        Main collection loop: collect pod metrics and send to backend.
        """
        logger.info("Starting pod metrics collection cycle")

        try:
            # Collect pod metrics
            pod_metrics = self.collect_pod_metrics()

            # Send to backend
            if pod_metrics:
                self.send_pod_metrics_batch(pod_metrics)
            else:
                logger.info("No pod metrics collected (this is normal for nodes with no pods)")

        except Exception as e:
            logger.error(f"Error in pod metrics collection cycle: {e}", exc_info=True)

        logger.info("Pod metrics collection cycle complete")

    def run(self):
        """
        Run the pod metrics collector in a loop.
        """
        self.running = True
        logger.info(f"Starting pod metrics collector with {self.collection_interval}s interval")

        while self.running:
            try:
                self.collect_and_send()
            except Exception as e:
                logger.error(f"Error in collection cycle: {e}", exc_info=True)

            # Wait for next collection interval
            time.sleep(self.collection_interval)

        logger.info("Pod metrics collector stopped")

    def stop(self):
        """
        Stop the pod metrics collector.
        """
        logger.info("Stopping pod metrics collector...")
        self.running = False
