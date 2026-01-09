#!/usr/bin/env python3
"""
Kubernetes Action Actuator Module

This module executes actions on Kubernetes clusters based on commands from the backend:
- Evict pods
- Cordon/uncordon nodes
- Drain nodes
- Update deployments
- Label/taint nodes

All actions are verified with HMAC signatures and results are reported back.
"""

import os
import sys
import time
import hmac
import hashlib
import json
import logging
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ActionActuator:
    """
    Executes actions on Kubernetes cluster based on backend commands.
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str, secret_key: str):
        """
        Initialize the action actuator.

        Args:
            backend_url: URL of the backend API
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
            secret_key: Secret key for HMAC verification
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.secret_key = secret_key.encode('utf-8')
        self.poll_interval = int(os.getenv('ACTION_POLL_INTERVAL', '10'))
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
        self.apps_v1 = client.AppsV1Api()

        logger.info(f"ActionActuator initialized for cluster: {cluster_id}")

    def verify_signature(self, payload: Dict[str, Any], signature: str) -> bool:
        """
        Verify HMAC signature of action payload.

        Args:
            payload: Action payload dictionary
            signature: Expected HMAC signature

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            payload_str = json.dumps(payload, sort_keys=True)
            computed_signature = hmac.new(
                self.secret_key,
                payload_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(computed_signature, signature)

        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    def evict_pod(self, namespace: str, pod_name: str,
                  grace_period: int = 30) -> Dict[str, Any]:
        """
        Evict a pod from its node.

        Args:
            namespace: Pod namespace
            pod_name: Pod name
            grace_period: Grace period in seconds

        Returns:
            Result dictionary with success status and message
        """
        logger.info(f"Evicting pod {namespace}/{pod_name}")

        try:
            # Create eviction object
            eviction = client.V1Eviction(
                metadata=client.V1ObjectMeta(
                    name=pod_name,
                    namespace=namespace
                ),
                delete_options=client.V1DeleteOptions(
                    grace_period_seconds=grace_period
                )
            )

            # Execute eviction
            self.core_v1.create_namespaced_pod_eviction(
                name=pod_name,
                namespace=namespace,
                body=eviction
            )

            logger.info(f"Successfully evicted pod {namespace}/{pod_name}")
            return {
                'success': True,
                'message': f'Pod {namespace}/{pod_name} evicted successfully'
            }

        except ApiException as e:
            error_msg = f"Failed to evict pod {namespace}/{pod_name}: {e.reason}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error evicting pod {namespace}/{pod_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }

    def cordon_node(self, node_name: str, uncordon: bool = False) -> Dict[str, Any]:
        """
        Cordon or uncordon a node.

        Args:
            node_name: Name of the node
            uncordon: If True, uncordon the node; if False, cordon it

        Returns:
            Result dictionary with success status and message
        """
        action = "Uncordoning" if uncordon else "Cordoning"
        logger.info(f"{action} node {node_name}")

        try:
            # Get current node
            node = self.core_v1.read_node(node_name)

            # Update schedulable status
            node.spec.unschedulable = not uncordon

            # Patch the node
            self.core_v1.patch_node(node_name, node)

            logger.info(f"Successfully {action.lower()} node {node_name}")
            return {
                'success': True,
                'message': f'Node {node_name} {action.lower()} successfully'
            }

        except ApiException as e:
            error_msg = f"Failed to {action.lower()} node {node_name}: {e.reason}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error {action.lower()} node {node_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }

    def drain_node(self, node_name: str, force: bool = False,
                   grace_period: int = 30) -> Dict[str, Any]:
        """
        Drain a node by evicting all pods.

        Args:
            node_name: Name of the node
            force: Force drain even if there are pods not managed by ReplicationController
            grace_period: Grace period for pod eviction

        Returns:
            Result dictionary with success status and message
        """
        logger.info(f"Draining node {node_name}")

        try:
            # First, cordon the node
            cordon_result = self.cordon_node(node_name, uncordon=False)
            if not cordon_result['success']:
                return cordon_result

            # Get all pods on the node
            pods = self.core_v1.list_pod_for_all_namespaces(
                field_selector=f'spec.nodeName={node_name}'
            )

            eviction_results = []
            failed_evictions = []

            for pod in pods.items:
                # Skip daemonset pods and mirror pods
                if self._is_daemonset_pod(pod) or self._is_mirror_pod(pod):
                    logger.info(f"Skipping system pod {pod.metadata.namespace}/{pod.metadata.name}")
                    continue

                # Check if pod is managed by a controller
                if not force and not self._has_controller(pod):
                    msg = f"Pod {pod.metadata.namespace}/{pod.metadata.name} not managed by controller"
                    logger.warning(msg)
                    failed_evictions.append(msg)
                    continue

                # Evict the pod
                result = self.evict_pod(
                    pod.metadata.namespace,
                    pod.metadata.name,
                    grace_period
                )
                eviction_results.append(result)

                if not result['success']:
                    failed_evictions.append(result['message'])

            if failed_evictions:
                return {
                    'success': False,
                    'message': f'Failed to drain node {node_name}',
                    'evicted': len([r for r in eviction_results if r['success']]),
                    'failed': len(failed_evictions),
                    'errors': failed_evictions
                }

            logger.info(f"Successfully drained node {node_name}")
            return {
                'success': True,
                'message': f'Node {node_name} drained successfully',
                'evicted': len(eviction_results)
            }

        except ApiException as e:
            error_msg = f"Failed to drain node {node_name}: {e.reason}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error draining node {node_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }

    def label_node(self, node_name: str, labels: Dict[str, str],
                   remove: bool = False) -> Dict[str, Any]:
        """
        Add or remove labels from a node.

        Args:
            node_name: Name of the node
            labels: Dictionary of labels to add or remove
            remove: If True, remove the labels; if False, add them

        Returns:
            Result dictionary with success status and message
        """
        action = "Removing" if remove else "Adding"
        logger.info(f"{action} labels on node {node_name}: {labels}")

        try:
            # Get current node
            node = self.core_v1.read_node(node_name)

            if remove:
                # Remove labels
                for key in labels.keys():
                    if key in node.metadata.labels:
                        del node.metadata.labels[key]
            else:
                # Add labels
                if node.metadata.labels is None:
                    node.metadata.labels = {}
                node.metadata.labels.update(labels)

            # Patch the node
            self.core_v1.patch_node(node_name, node)

            logger.info(f"Successfully {action.lower()} labels on node {node_name}")
            return {
                'success': True,
                'message': f'Labels {action.lower()} on node {node_name} successfully'
            }

        except ApiException as e:
            error_msg = f"Failed to {action.lower()} labels on node {node_name}: {e.reason}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error {action.lower()} labels on node {node_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }

    def update_deployment(self, namespace: str, deployment_name: str,
                         replicas: Optional[int] = None,
                         image: Optional[str] = None) -> Dict[str, Any]:
        """
        Update a deployment's replicas or image.

        Args:
            namespace: Deployment namespace
            deployment_name: Deployment name
            replicas: New replica count (optional)
            image: New image for first container (optional)

        Returns:
            Result dictionary with success status and message
        """
        logger.info(f"Updating deployment {namespace}/{deployment_name}")

        try:
            # Get current deployment
            deployment = self.apps_v1.read_namespaced_deployment(
                deployment_name,
                namespace
            )

            # Update replicas if specified
            if replicas is not None:
                deployment.spec.replicas = replicas
                logger.info(f"Setting replicas to {replicas}")

            # Update image if specified
            if image is not None and deployment.spec.template.spec.containers:
                deployment.spec.template.spec.containers[0].image = image
                logger.info(f"Setting image to {image}")

            # Patch the deployment
            self.apps_v1.patch_namespaced_deployment(
                deployment_name,
                namespace,
                deployment
            )

            logger.info(f"Successfully updated deployment {namespace}/{deployment_name}")
            return {
                'success': True,
                'message': f'Deployment {namespace}/{deployment_name} updated successfully'
            }

        except ApiException as e:
            error_msg = f"Failed to update deployment {namespace}/{deployment_name}: {e.reason}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error updating deployment {namespace}/{deployment_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }

    def _is_daemonset_pod(self, pod: client.V1Pod) -> bool:
        """Check if pod is managed by a DaemonSet."""
        if pod.metadata.owner_references:
            for ref in pod.metadata.owner_references:
                if ref.kind == 'DaemonSet':
                    return True
        return False

    def _is_mirror_pod(self, pod: client.V1Pod) -> bool:
        """Check if pod is a mirror pod (static pod)."""
        return pod.metadata.annotations and \
               'kubernetes.io/config.mirror' in pod.metadata.annotations

    def _has_controller(self, pod: client.V1Pod) -> bool:
        """Check if pod is managed by a controller."""
        return pod.metadata.owner_references is not None and \
               len(pod.metadata.owner_references) > 0

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single action.

        Args:
            action: Action dictionary containing type and parameters

        Returns:
            Result dictionary with success status and message
        """
        action_type = action.get('type')
        params = action.get('parameters', {})

        logger.info(f"Executing action: {action_type}")

        if action_type == 'evict_pod':
            return self.evict_pod(
                params['namespace'],
                params['pod_name'],
                params.get('grace_period', 30)
            )

        elif action_type == 'cordon_node':
            return self.cordon_node(
                params['node_name'],
                uncordon=False
            )

        elif action_type == 'uncordon_node':
            return self.cordon_node(
                params['node_name'],
                uncordon=True
            )

        elif action_type == 'drain_node':
            return self.drain_node(
                params['node_name'],
                params.get('force', False),
                params.get('grace_period', 30)
            )

        elif action_type == 'label_node':
            return self.label_node(
                params['node_name'],
                params['labels'],
                params.get('remove', False)
            )

        elif action_type == 'update_deployment':
            return self.update_deployment(
                params['namespace'],
                params['deployment_name'],
                params.get('replicas'),
                params.get('image')
            )

        else:
            return {
                'success': False,
                'message': f'Unknown action type: {action_type}'
            }

    def poll_actions(self) -> List[Dict[str, Any]]:
        """
        Poll backend for pending actions.

        Returns:
            List of action dictionaries
        """
        url = f"{self.backend_url}/api/v1/actions/poll"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        params = {'cluster_id': self.cluster_id}

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            actions = data.get('actions', [])

            if actions:
                logger.info(f"Received {len(actions)} pending actions")

            return actions

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to poll actions from backend: {e}")
            return []

    def report_action_result(self, action_id: str, result: Dict[str, Any]) -> bool:
        """
        Report action execution result to backend.

        Args:
            action_id: Unique action identifier
            result: Result dictionary

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.backend_url}/api/v1/actions/{action_id}/result"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'result': result,
            'timestamp': datetime.utcnow().isoformat()
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Successfully reported result for action {action_id}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to report action result: {e}")
            return False

    def run(self):
        """
        Run the action actuator in a loop.
        """
        self.running = True
        logger.info(f"Starting action actuator with {self.poll_interval}s poll interval")

        while self.running:
            try:
                # Poll for actions
                actions = self.poll_actions()

                # Execute each action
                for action in actions:
                    action_id = action.get('id')
                    signature = action.get('signature')

                    # Verify signature
                    if not self.verify_signature(action, signature):
                        logger.error(f"Invalid signature for action {action_id}")
                        self.report_action_result(action_id, {
                            'success': False,
                            'message': 'Invalid signature'
                        })
                        continue

                    # Execute action
                    result = self.execute_action(action)

                    # Report result
                    self.report_action_result(action_id, result)

            except Exception as e:
                logger.error(f"Error in actuator loop: {e}", exc_info=True)

            # Wait for next poll
            time.sleep(self.poll_interval)

        logger.info("Action actuator stopped")

    def stop(self):
        """
        Stop the action actuator.
        """
        logger.info("Stopping action actuator...")
        self.running = False


if __name__ == '__main__':
    # Test the actuator
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
    api_key = os.getenv('API_KEY', 'test-key')
    cluster_id = os.getenv('CLUSTER_ID', 'test-cluster')
    secret_key = os.getenv('SECRET_KEY', 'test-secret')

    actuator = ActionActuator(backend_url, api_key, cluster_id, secret_key)

    try:
        actuator.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        actuator.stop()
        sys.exit(0)
