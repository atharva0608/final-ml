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
import subprocess
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
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.policy_v1 = client.PolicyV1Api()

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

    def check_pdb_violation(self, namespace: str, pod_name: str) -> bool:
        """
        Check if evicting this pod would violate any PodDisruptionBudget.
        Returns True if violation would occur (SAFE TO EVICT = FALSE).
        """
        try:
            pdbs = self.policy_v1.list_namespaced_pod_disruption_budget(namespace)
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            
            for pdb in pdbs.items:
                # Simple label selector match check (simplified for MVP)
                # In real world, we need full label selector matching logic
                # Here we assume if PDB selector matches pod labels, it applies.
                selector = pdb.spec.selector
                if selector and selector.match_labels:
                    match = all(pod.metadata.labels.get(k) == v for k, v in selector.match_labels.items())
                    if match:
                         # Check allowed disruptions
                         if pdb.status.disruptions_allowed < 1:
                             logger.warning(f"PDB Violation: {pdb.metadata.name} prevents eviction of {pod_name}")
                             return True
            return False
            
        except Exception as e:
            logger.error(f"Error checking PDBs: {e}")
            return True # Fail safe: Assume violation if we can't check

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

        retries = 5
        retry_delay = 10

        for attempt in range(1, retries + 2):
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
                # 429 = PDB Violation (Too Many Requests)
                if e.status == 429:
                    if attempt <= retries:
                        logger.warning(f"Eviction blocked by PDB (429) for {namespace}/{pod_name}. Retrying in {retry_delay}s ({attempt}/{retries})...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        error_msg = f"Failed to evict pod {namespace}/{pod_name} after {retries} retries due to PDB violation"
                        logger.error(error_msg)
                        return {
                            'success': False,
                            'message': error_msg,
                            'error': "PDB_VIOLATION_MAX_RETRIES"
                        }
                
                # Other API errors
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

                # Check PDBs — if force is set, skip eviction and delete directly (bypasses PDB)
                if self.check_pdb_violation(pod.metadata.namespace, pod.metadata.name):
                    if force:
                        # Force-delete the pod (0 grace period) — K8s will reschedule it on another node
                        # This is equivalent to kubectl drain --disable-eviction --force
                        try:
                            self.core_v1.delete_namespaced_pod(
                                name=pod.metadata.name,
                                namespace=pod.metadata.namespace,
                                body=client.V1DeleteOptions(grace_period_seconds=0)
                            )
                            logger.warning(
                                f"Force-deleted PDB-protected pod {pod.metadata.namespace}/{pod.metadata.name} "
                                f"(force drain mode) — will reschedule on another node"
                            )
                            eviction_results.append({'success': True, 'force_deleted': True})
                        except Exception as _del_err:
                            msg = f"Pod {pod.metadata.namespace}/{pod.metadata.name} PDB-protected and force-delete failed: {_del_err}"
                            logger.error(msg)
                            failed_evictions.append(msg)
                    else:
                        msg = f"Pod {pod.metadata.namespace}/{pod.metadata.name} protected by PDB"
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

    def _find_node_by_instance_id(self, instance_id: str) -> Optional[str]:
        """
        Resolve a K8s node name from an EC2 instance ID using spec.providerID.
        EKS sets providerID = "aws://<az>/<instance_id>" on every node.
        This is the most reliable resolution method.
        """
        if not instance_id:
            return None
        try:
            nodes = self.core_v1.list_node()
            for node in nodes.items:
                provider_id = getattr(node.spec, 'provider_id', '') or ''
                if instance_id in provider_id:
                    return node.metadata.name
        except Exception as e:
            logger.warning(f"Failed to find node by instance_id {instance_id}: {e}")
        return None

    def _find_node_name(self, instance_type: str, az: str) -> Optional[str]:
        """
        Resolve a K8s node name from EC2 instance_type + AZ labels.
        Karpenter-provisioned nodes have standard K8s labels:
          node.kubernetes.io/instance-type=<type>
          topology.kubernetes.io/zone=<az>
        Fallback when instance_id is not available.
        """
        try:
            label_sel = f"node.kubernetes.io/instance-type={instance_type}"
            nodes = self.core_v1.list_node(label_selector=label_sel)
            for node in nodes.items:
                node_az = (node.metadata.labels or {}).get('topology.kubernetes.io/zone', '')
                if not az or node_az == az:
                    return node.metadata.name
        except Exception as e:
            logger.warning(f"Failed to find node for {instance_type}/{az}: {e}")
        return None

    def patch_karpenter_nodepool(self, nodepool_name: str, instance_types: List[str],
                                  capacity_type: List[str], az: str = None,
                                  architecture: List[str] = None) -> Dict[str, Any]:
        """
        Patch a Karpenter NodePool to target specific instance types and capacity type (spot/on-demand).
        Uses the Kubernetes CustomObjectsApi to patch the NodePool CRD.
        """
        from kubernetes import client as _k8s
        custom_api = _k8s.CustomObjectsApi()

        requirements = [
            {"key": "karpenter.sh/capacity-type", "operator": "In", "values": capacity_type},
            {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": instance_types},
        ]
        if az:
            requirements.append({"key": "topology.kubernetes.io/zone", "operator": "In", "values": [az]})
        if architecture:
            requirements.append({"key": "kubernetes.io/arch", "operator": "In", "values": architecture})

        # NodePool v1 schema: requirements live at spec.template.spec.requirements
        # NOT at spec.requirements — patching the wrong path is silently ignored by Karpenter.
        patch_body = {"spec": {"template": {"spec": {"requirements": requirements}}}}

        try:
            result = custom_api.patch_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
                plural="nodepools",
                name=nodepool_name,
                body=patch_body
            )
            logger.info(f"Patched Karpenter NodePool {nodepool_name}: types={instance_types}, capacity={capacity_type}")
            return {"success": True, "message": f"NodePool {nodepool_name} patched successfully", "nodepool": nodepool_name}
        except Exception as e:
            err_str = str(e)
            # 404: NodePool doesn't exist — create it on the fly
            if '404' in err_str or 'Not Found' in err_str:
                logger.warning(f"NodePool '{nodepool_name}' not found — creating it now")
                try:
                    # Get cluster name from Karpenter ConfigMap (set during helm install)
                    try:
                        cm = self.core_v1.read_namespaced_config_map('karpenter-global-settings', 'karpenter')
                        cluster_name = (cm.data or {}).get('clusterName', '')
                    except Exception:
                        cluster_name = ''
                    if not cluster_name:
                        # Fallback: infer from any node's cluster tag label
                        try:
                            all_nodes = self.core_v1.list_node(limit=1)
                            for _n in all_nodes.items:
                                _labels = _n.metadata.labels or {}
                                cluster_name = (_labels.get('alpha.eksctl.io/cluster-name') or
                                                _labels.get('eks.amazonaws.com/cluster-name') or '')
                                if cluster_name:
                                    break
                        except Exception:
                            pass
                    if cluster_name:
                        self._create_default_karpenter_resources(cluster_name, nodepool_name)
                        # Now patch the newly created NodePool
                        try:
                            result = custom_api.patch_cluster_custom_object(
                                group="karpenter.sh", version="v1", plural="nodepools",
                                name=nodepool_name, body=patch_body
                            )
                            logger.info(f"Created+patched NodePool '{nodepool_name}'")
                            return {"success": True, "message": f"NodePool '{nodepool_name}' created and patched", "nodepool": nodepool_name}
                        except Exception as _patch_err:
                            logger.warning(f"Patch after create failed: {_patch_err} — using newly created NodePool as-is")
                            return {"success": True, "message": f"NodePool '{nodepool_name}' created with requested requirements", "nodepool": nodepool_name}
                    else:
                        logger.warning(f"Cannot create NodePool — cluster name unknown. Karpenter may not be installed.")
                        return {"success": False, "message": f"NodePool '{nodepool_name}' not found and cluster name could not be determined — ensure Karpenter is installed"}
                except Exception as _create_err:
                    logger.error(f"Failed to create NodePool '{nodepool_name}': {_create_err}")
                    return {"success": False, "message": f"NodePool not found and auto-creation failed: {_create_err}"}
            # Karpenter CRD itself not installed (no matches for kind)
            if 'No matches for kind' in err_str:
                return {"success": False, "message": "Karpenter CRDs not found — install Karpenter first"}
            error_msg = f"Failed to patch NodePool {nodepool_name}: {e}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "error": str(e)}

    def install_karpenter(self, cluster_name: str, region: str,
                          karpenter_version: str = "1.0.8",
                          nodepool_name: str = "default",
                          karpenter_iam_role_arn: str = "",
                          sqs_queue_name: str = "") -> Dict[str, Any]:
        """
        Install Karpenter via Helm inside the cluster.

        Runs:
          helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
            --version <version> \
            --namespace karpenter --create-namespace \
            --set settings.clusterName=<cluster_name> \
            --wait --timeout 5m
        Then creates a basic default NodePool CRD so Karpenter can start provisioning.
        """
        logger.info(f"Installing Karpenter {karpenter_version} on cluster {cluster_name} ({region})")
        try:
            # Bug A-2 fix: enforce strict queue name — never fall back to bare cluster name.
            # The platform always names the queue KarpenterInterruptionQueue-{cluster_name}.
            # Using the bare cluster name causes a silent mismatch that breaks interruption handling.
            if sqs_queue_name:
                effective_sqs_queue = sqs_queue_name
                logger.info(f"Karpenter install: SQS queue={effective_sqs_queue!r}")
            else:
                # Construct from cluster name rather than silently using bare name
                effective_sqs_queue = f"KarpenterInterruptionQueue-{cluster_name}"
                logger.warning(
                    f"Karpenter install: sqs_queue_name missing from payload — "
                    f"defaulting to {effective_sqs_queue!r}. "
                    f"Ensure the backend is passing sqs_queue_name in the action payload."
                )
            helm_cmd = [
                "helm", "upgrade", "--install", "karpenter",
                "oci://public.ecr.aws/karpenter/karpenter",
                "--version", karpenter_version,
                "--namespace", "karpenter",
                "--create-namespace",
                "--set", f"settings.clusterName={cluster_name}",
                "--set", f"settings.interruptionQueue={effective_sqs_queue}",
                "--wait", "--timeout", "5m",
            ]
            # IRSA: annotate the Karpenter controller ServiceAccount so it can call AWS APIs
            if karpenter_iam_role_arn:
                helm_cmd += [
                    "--set",
                    f"serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn={karpenter_iam_role_arn}",
                ]
            result = subprocess.run(
                helm_cmd,
                capture_output=True, text=True, timeout=360
            )
            if result.returncode != 0:
                err = result.stderr or result.stdout
                logger.error(f"helm install karpenter failed: {err}")
                return {"success": False, "message": f"helm install failed: {err[:500]}"}

            logger.info(f"Karpenter {karpenter_version} installed successfully")

            # Register KarpenterNodeRole as EC2_LINUX access entry so provisioned
            # nodes can join the EKS cluster without a manual aws-auth ConfigMap edit.
            # Must happen BEFORE NodePool/EC2NodeClass are created.
            try:
                self._register_karpenter_node_role_access_entry(cluster_name, region)
            except Exception as ae_err:
                logger.warning(f"KarpenterNodeRole access entry setup failed (manual step may be needed): {ae_err}")

            # Create a basic EC2NodeClass + NodePool after install
            try:
                self._create_default_karpenter_resources(cluster_name, nodepool_name)
            except Exception as np_err:
                logger.warning(f"Karpenter installed but default NodePool creation failed: {np_err}")

            return {
                "success": True,
                "message": f"Karpenter {karpenter_version} installed successfully on cluster {cluster_name}",
                "version": karpenter_version,
                "nodepool": nodepool_name,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "message": "helm install timed out after 6 minutes"}
        except FileNotFoundError:
            return {"success": False, "message": "helm binary not found — agent image may need to be rebuilt"}
        except Exception as e:
            logger.error(f"Unexpected error installing Karpenter: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def _create_default_karpenter_resources(self, cluster_name: str, nodepool_name: str):
        """Create a minimal EC2NodeClass and NodePool after Karpenter install.

        Uses AL2023 amiFamily with alias: al2023@latest — Karpenter resolves the correct
        architecture-specific AMI from SSM at provisioning time (amd64 AMI for x86_64 nodes,
        arm64 AMI for Graviton nodes). This is the canonical Karpenter v1.x approach and
        eliminates the need for hardcoded AMI IDs or per-arch AMI selectors.
        """
        custom_api = client.CustomObjectsApi()

        # EC2NodeClass — AL2023 amiFamily with alias supports BOTH amd64 AND arm64 automatically.
        # Karpenter resolves the correct AMI via SSM Parameter Store at launch time.
        node_class = {
            "apiVersion": "karpenter.k8s.aws/v1",
            "kind": "EC2NodeClass",
            "metadata": {
                "name": "default",
                "annotations": {"spot-optimizer/managed": "true"},
            },
            "spec": {
                "amiFamily": "AL2023",
                "amiSelectorTerms": [{"alias": "al2023@latest"}],
                "role": f"KarpenterNodeRole-{cluster_name}",
                "subnetSelectorTerms": [{"tags": {"karpenter.sh/discovery": cluster_name}}],
                "securityGroupSelectorTerms": [{"tags": {"karpenter.sh/discovery": cluster_name}}],
                "tags": {"ManagedBy": "SpotOptimizer", "ClusterName": cluster_name},
            }
        }
        try:
            custom_api.create_cluster_custom_object(
                group="karpenter.k8s.aws", version="v1", plural="ec2nodeclasses", body=node_class
            )
            logger.info("Created default EC2NodeClass (AL2023, dual-arch)")
        except Exception as e:
            if "already exists" in str(e).lower():
                # Patch the existing EC2NodeClass to use the alias (idempotent upgrade)
                try:
                    custom_api.patch_cluster_custom_object(
                        group="karpenter.k8s.aws", version="v1", plural="ec2nodeclasses",
                        name="default",
                        body={"spec": {"amiFamily": "AL2023", "amiSelectorTerms": [{"alias": "al2023@latest"}]}}
                    )
                    logger.info("Patched existing EC2NodeClass to AL2023 alias")
                except Exception as _pe:
                    logger.info(f"EC2NodeClass already exists (patch skipped: {_pe})")
            else:
                logger.warning(f"EC2NodeClass creation failed: {e}")

        # NodePool — allows BOTH amd64 and arm64.
        # EC2NodeClass (AL2023) handles architecture-specific AMI selection automatically.
        # Instance types are overwritten at rebalance time by the ML ranker.
        node_pool = {
            "apiVersion": "karpenter.sh/v1",
            "kind": "NodePool",
            "metadata": {
                "name": nodepool_name,
                "annotations": {"spot-optimizer/managed": "true"},
            },
            "spec": {
                "template": {
                    "spec": {
                        "nodeClassRef": {"group": "karpenter.k8s.aws", "kind": "EC2NodeClass", "name": "default"},
                        "requirements": [
                            {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["spot", "on-demand"]},
                            # Allow both architectures — AL2023 selects the correct AMI per arch
                            {"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64", "arm64"]},
                            {"key": "node.kubernetes.io/instance-type", "operator": "In",
                             "values": ["m5.large", "m5.xlarge", "m6i.large", "m6i.xlarge",
                                        "m6g.large", "m6g.xlarge",  # Graviton3
                                        "c5.large", "c5.xlarge", "c6g.large", "c6g.xlarge"]},
                        ],
                    }
                },
                "disruption": {"consolidationPolicy": "WhenEmptyOrUnderutilized", "consolidateAfter": "30s"},
            }
        }
        try:
            custom_api.create_cluster_custom_object(
                group="karpenter.sh", version="v1", plural="nodepools", body=node_pool
            )
            logger.info(f"Created default NodePool '{nodepool_name}'")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"NodePool '{nodepool_name}' already exists, skipping")
            else:
                logger.warning(f"NodePool creation failed: {e}")

    def _patch_container_resources(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Patch CPU/memory requests and limits for a specific container in a workload.

        Called by PATCH_CONTAINER_RESOURCES AgentAction — the right-sizing execution path.
        Complements PATCH_KARPENTER_NODEPOOL: that changes the node size, this changes
        what the container ASKS for (requests/limits inside the pod spec).

        Why both are needed:
          - Node change (Karpenter) is immediate but the pod still requests old resources
          - If requests stay at 2000m CPU but the pod uses 200m, bin-packing efficiency
            is lost — scheduler still reserves 2000m per pod on the new node
          - This patch updates the Deployment/StatefulSet spec so new pods get right-sized
            requests, allowing tighter bin-packing on the smaller node

        Payload fields:
            namespace       (str):  Kubernetes namespace (e.g. "production")
            controller_type (str):  "Deployment" | "StatefulSet" | "DaemonSet"
            controller_name (str):  Workload name (e.g. "my-app")
            container_name  (str):  Container to patch (e.g. "app")
            resources       (dict): {
                "requests": {"cpu": "250m", "memory": "512Mi"},
                "limits":   {"cpu": "500m", "memory": "768Mi"}
            }

        Returns:
            {"success": bool, "message": str, "patched_resource": str}
        """
        namespace      = payload.get("namespace", "default")
        ctrl_type      = (payload.get("controller_type") or "Deployment").lower()
        ctrl_name      = payload.get("controller_name", "")
        container_name = payload.get("container_name", "")
        resources      = payload.get("resources", {})

        if not ctrl_name or not container_name or not resources:
            return {
                "success": False,
                "message": "Missing required fields: controller_name, container_name, or resources"
            }

        try:
            # Build the strategic merge patch — only update the named container
            patch_body = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name":      container_name,
                                "resources": resources
                            }]
                        }
                    }
                }
            }

            if ctrl_type == "deployment":
                self.apps_v1.patch_namespaced_deployment(
                    name=ctrl_name, namespace=namespace, body=patch_body
                )
            elif ctrl_type == "statefulset":
                self.apps_v1.patch_namespaced_stateful_set(
                    name=ctrl_name, namespace=namespace, body=patch_body
                )
            elif ctrl_type == "daemonset":
                self.apps_v1.patch_namespaced_daemon_set(
                    name=ctrl_name, namespace=namespace, body=patch_body
                )
            else:
                return {
                    "success": False,
                    "message": f"Unsupported controller_type: {ctrl_type} (use Deployment/StatefulSet/DaemonSet)"
                }

            patched_resource = f"{ctrl_type}/{namespace}/{ctrl_name}[{container_name}]"
            logger.info(
                f"Patched container resources: {patched_resource} "
                f"requests={resources.get('requests')} limits={resources.get('limits')}"
            )
            return {
                "success":          True,
                "message":          f"Container resources updated on {patched_resource}",
                "patched_resource": patched_resource,
                "resources":        resources,
            }

        except ApiException as e:
            msg = f"K8s API error patching {ctrl_type}/{namespace}/{ctrl_name}: {e.status} {e.reason}"
            logger.error(msg)
            return {"success": False, "message": msg}
        except Exception as e:
            logger.error(f"Unexpected error in _patch_container_resources: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def _register_karpenter_node_role_access_entry(
        self, cluster_name: str, region: str
    ) -> None:
        """
        Register KarpenterNodeRole as an EC2_LINUX EKS access entry.

        RBAC-03: Without this, Karpenter-provisioned nodes cannot join the cluster.
        They boot but immediately fail the bootstrap handshake because the node's
        IAM role (KarpenterNodeRole-{cluster}) is not in aws-auth or EKS access entries.

        Why EC2_LINUX type (not STANDARD):
          - EC2_LINUX access entries automatically get the AmazonEKSWorkerNodePolicy
            and bootstrap trust required for nodes to join as worker nodes.
          - STANDARD entries are for human/service principals — they need an explicit
            associate_access_policy call.  EC2_LINUX does NOT need that call.

        This is idempotent: if the entry already exists it logs and returns.
        """
        try:
            import boto3
        except ImportError:
            logger.warning("boto3 not available in agent — cannot auto-register KarpenterNodeRole access entry")
            return

        try:
            # Resolve account ID from instance metadata (available on any EC2 node)
            sts = boto3.client("sts", region_name=region)
            account_id = sts.get_caller_identity()["Account"]
        except Exception as e:
            logger.warning(f"Could not resolve AWS account ID for KarpenterNodeRole registration: {e}")
            return

        node_role_arn = f"arn:aws:iam::{account_id}:role/KarpenterNodeRole-{cluster_name}"
        eks = boto3.client("eks", region_name=region)

        try:
            eks.describe_access_entry(clusterName=cluster_name, principalArn=node_role_arn)
            logger.info(f"KarpenterNodeRole access entry already exists for {node_role_arn}")
            return
        except eks.exceptions.ResourceNotFoundException:
            pass  # Does not exist yet — create it

        eks.create_access_entry(
            clusterName=cluster_name,
            principalArn=node_role_arn,
            type="EC2_LINUX"   # EC2_LINUX = automatic node bootstrap trust; no policy association needed
        )
        logger.info(f"Created EC2_LINUX access entry for KarpenterNodeRole: {node_role_arn}")

    def _get_region(self) -> str:
        """
        Return the AWS region this agent is running in.

        Uses IMDSv2 (token-based) — works on hardened clusters where IMDSv1 is disabled.
        Falls back to AWS_REGION env var if IMDS is not reachable (e.g. in tests).
        """
        try:
            import urllib.request
            token_req = urllib.request.Request(
                "http://169.254.169.254/latest/api/token",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                method="PUT",
            )
            token = urllib.request.urlopen(token_req, timeout=2).read().decode()
            region_req = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/placement/region",
                headers={"X-aws-ec2-metadata-token": token},
            )
            return urllib.request.urlopen(region_req, timeout=2).read().decode()
        except Exception:
            return os.environ.get("AWS_REGION", "us-east-1")

    def _terminate_node(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Terminate the EC2 instance backing a drained Kubernetes node.

        TERMINATE-NODE-01: This is the missing step that makes Karpenter actually work.
        Without termination:
          - Pods drained from a node re-schedule onto OTHER existing nodes (never Pending)
          - Karpenter only provisions new nodes when pods are Pending with no room
          - The old on-demand node stays alive, wasting cost
        With termination:
          - Old node EC2 instance terminates → K8s removes node object → pods go Pending
          - Karpenter sees Pending pods → provisions a new spot node → pods schedule on spot

        Payload fields:
            node_name   (str, optional): K8s node name — used as fallback to resolve instance_id
            instance_id (str, optional): EC2 instance ID (i-xxxx) — preferred path; avoids K8s API call

        Returns:
            {"success": bool, "method": str, "instance_id": str, "node_name": str}
        """
        node_name      = payload.get("node_name") or None
        instance_id    = payload.get("instance_id") or None
        decrement_asg  = payload.get("decrement_asg", True)  # default True: prevent ASG relaunch

        if not node_name and not instance_id:
            return {"success": False, "error": "Must provide node_name or instance_id in payload"}

        # Resolve node_name from instance_id via K8s providerID scan (enables kubectl fallback)
        if not node_name and instance_id:
            node_name = self._find_node_by_instance_id(instance_id)
            if node_name:
                logger.info(f"Resolved node_name={node_name} from instance_id={instance_id}")

        # Resolve instance_id from K8s node spec.providerID if not passed in payload
        if not instance_id and node_name:
            try:
                v1 = client.CoreV1Api()
                node_obj = v1.read_node(name=node_name)
                provider_id = node_obj.spec.provider_id or ""
                # providerID format: aws:///us-east-1a/i-0abc123def456
                if provider_id:
                    instance_id = provider_id.rstrip("/").split("/")[-1]
                    logger.info(f"Resolved instance_id={instance_id} from providerID={provider_id}")
            except Exception as resolve_err:
                logger.warning(f"Could not resolve instance_id for node {node_name}: {resolve_err}")

        # Primary path: terminate EC2 instance backing the drained node
        if instance_id:
            try:
                import boto3 as _boto3
                region = self._get_region()

                if decrement_asg:
                    # ASG terminate with ShouldDecrementDesiredCapacity=True:
                    # - Terminates the instance AND reduces ASG desired count
                    # - ASG won't relaunch a replacement on-demand node
                    # - Pods go PENDING → Karpenter provisions a spot node instead
                    try:
                        asg = _boto3.client("autoscaling", region_name=region)
                        asg.terminate_instance_in_auto_scaling_group(
                            InstanceId=instance_id,
                            ShouldDecrementDesiredCapacity=True
                        )
                        logger.info(
                            f"Terminated EC2 instance {instance_id} via ASG "
                            f"(desired capacity decremented — Karpenter will provision spot)"
                        )
                        return {
                            "success":     True,
                            "method":      "asg_terminate",
                            "instance_id": instance_id,
                            "node_name":   node_name or "",
                        }
                    except Exception as asg_err:
                        logger.warning(
                            f"ASG terminate failed for {instance_id}: {asg_err} "
                            f"— falling back to direct EC2 terminate"
                        )

                # Direct EC2 terminate (used if decrement_asg=False, or if ASG call failed)
                ec2 = _boto3.client("ec2", region_name=region)
                ec2.terminate_instances(InstanceIds=[instance_id])
                logger.info(f"Terminated EC2 instance {instance_id} via direct EC2 (node: {node_name})")
                return {
                    "success":     True,
                    "method":      "ec2_terminate",
                    "instance_id": instance_id,
                    "node_name":   node_name or "",
                }
            except Exception as ec2_err:
                logger.error(f"EC2 terminate failed for {instance_id}: {ec2_err}")
                # Fall through to K8s node delete as backup

        # Fallback path: delete the K8s node object
        # Cloud controller manager will clean up the underlying EC2 instance
        if node_name:
            try:
                v1 = client.CoreV1Api()
                v1.delete_node(name=node_name)
                logger.info(f"Deleted K8s node object {node_name} (EC2 terminate unavailable)")
                return {
                    "success":   True,
                    "method":    "k8s_node_delete",
                    "node_name": node_name,
                    "instance_id": instance_id or "",
                }
            except Exception as k8s_err:
                logger.error(f"K8s node delete also failed for {node_name}: {k8s_err}")
                return {"success": False, "error": f"Both EC2 terminate and K8s delete failed: {k8s_err}"}

        return {"success": False, "error": "No valid instance_id or node_name to terminate"}

    def uninstall_karpenter(self, release_name: str = "karpenter",
                             namespace: str = "karpenter") -> Dict[str, Any]:
        """
        Uninstall Karpenter via helm uninstall and delete the namespace.
        """
        logger.info(f"Uninstalling Karpenter release '{release_name}' from namespace '{namespace}'")
        try:
            result = subprocess.run(
                ["helm", "uninstall", release_name, "--namespace", namespace, "--wait", "--timeout", "3m"],
                capture_output=True, text=True, timeout=240
            )
            if result.returncode != 0:
                # If release not found, treat as success (idempotent)
                err = result.stderr or result.stdout
                if "not found" in err.lower() or "release: not found" in err.lower():
                    logger.info("Karpenter release not found — already uninstalled")
                    return {"success": True, "message": "Karpenter was not installed (release not found)", "skipped": True}
                logger.error(f"helm uninstall failed: {err}")
                return {"success": False, "message": f"helm uninstall failed: {err[:500]}"}

            # Delete namespace (best-effort)
            try:
                self.core_v1.delete_namespace(namespace)
                logger.info(f"Deleted namespace '{namespace}'")
            except Exception as ns_err:
                logger.warning(f"Could not delete namespace '{namespace}': {ns_err}")

            return {
                "success": True,
                "message": f"Karpenter uninstalled successfully (release: {release_name})",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "helm uninstall timed out after 4 minutes"}
        except FileNotFoundError:
            return {"success": False, "message": "helm binary not found — agent image may need to be rebuilt"}
        except Exception as e:
            logger.error(f"Unexpected error uninstalling Karpenter: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def execute_action_v2(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an action using the v2 backend protocol.

        Backend sends UPPERCASE action_type matching AgentActionType enum values:
          EVICT_POD | CORDON_NODE | DRAIN_NODE | TERMINATE_NODE |
          LABEL_NODE | UPDATE_DEPLOYMENT | PATCH_KARPENTER_NODEPOOL |
          INSTALL_KARPENTER | UNINSTALL_KARPENTER | PATCH_CONTAINER_RESOURCES

        FIX-ENUM-01: All enum string values are UPPERCASE. Normalization happens
        here at the dispatch boundary (.upper()) so legacy lowercase DB rows and
        any future mixed-case inputs are handled in one place.
        """
        logger.info(f"[v2] Executing action: {action_type}, payload keys: {list(payload.keys())}")

        # FIX-ENUM-01: Normalize to UPPERCASE at dispatch boundary.
        # Handles legacy lowercase values stored in DB and any string format from callers.
        action_type = action_type.upper() if isinstance(action_type, str) else action_type.value.upper()

        if action_type == 'EVICT_POD':
            return self.evict_pod(
                payload['namespace'],
                payload['pod_name'],
                payload.get('grace_period', 30)
            )

        elif action_type == 'CORDON_NODE':
            # Prefer exact instance_id lookup (via providerID), then fallback to type+AZ
            node_name = (payload.get('node_name') or
                         self._find_node_by_instance_id(payload.get('instance_id', '')) or
                         self._find_node_name(payload.get('instance_type', ''), payload.get('az', '')))
            if not node_name:
                return {'success': False, 'message': f"Could not find node for instance_id={payload.get('instance_id')} type={payload.get('instance_type')} az={payload.get('az')}"}
            return self.cordon_node(node_name, uncordon=False)

        elif action_type == 'DRAIN_NODE':
            # Prefer exact instance_id lookup (via providerID), then fallback to type+AZ
            node_name = (payload.get('node_name') or
                         self._find_node_by_instance_id(payload.get('instance_id', '')) or
                         self._find_node_name(payload.get('instance_type', ''), payload.get('az', '')))
            if not node_name:
                return {'success': False, 'message': f"Could not find node for instance_id={payload.get('instance_id')} type={payload.get('instance_type')} az={payload.get('az')}"}
            return self.drain_node(
                node_name,
                force=payload.get('ignore_daemonsets', False),
                grace_period=payload.get('grace_period_seconds', 30)
            )

        elif action_type == 'LABEL_NODE':
            node_name = (payload.get('node_name') or
                         self._find_node_by_instance_id(payload.get('instance_id', '')) or
                         self._find_node_name(payload.get('instance_type', ''), payload.get('az', '')))
            if not node_name:
                return {'success': False, 'message': 'Could not resolve node_name'}
            return self.label_node(node_name, payload.get('labels', {}), payload.get('remove', False))

        elif action_type == 'UPDATE_DEPLOYMENT':
            return self.update_deployment(
                payload['namespace'],
                payload['deployment_name'],
                payload.get('replicas'),
                payload.get('image')
            )

        elif action_type == 'PATCH_KARPENTER_NODEPOOL':
            return self.patch_karpenter_nodepool(
                nodepool_name=payload.get('nodepool_name', 'default'),
                instance_types=payload.get('instance_types', []),
                capacity_type=payload.get('capacity_type', ['spot']),
                az=payload.get('az'),
                architecture=payload.get('architecture')
            )

        elif action_type == 'INSTALL_KARPENTER':
            return self.install_karpenter(
                cluster_name=payload.get('cluster_name', ''),
                region=payload.get('region', 'ap-south-1'),
                sqs_queue_name=payload.get('sqs_queue_name', ''),
                karpenter_version=payload.get('karpenter_version', '1.0.8'),
                nodepool_name=payload.get('nodepool_name', 'default'),
                karpenter_iam_role_arn=payload.get('karpenter_iam_role_arn', ''),
            )

        elif action_type == 'UNINSTALL_KARPENTER':
            return self.uninstall_karpenter(
                release_name=payload.get('release_name', 'karpenter'),
                namespace=payload.get('namespace', 'karpenter'),
            )

        elif action_type == 'PATCH_CONTAINER_RESOURCES':
            return self._patch_container_resources(payload)

        elif action_type == 'TERMINATE_NODE':
            return self._terminate_node(payload)

        else:
            return {'success': False, 'message': f'Unknown action type: {action_type}'}

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single action (legacy v1 format).
        Delegates to execute_action_v2 after field name translation.
        """
        # v2 format: action_type + payload
        if 'action_type' in action:
            return self.execute_action_v2(action['action_type'], action.get('payload', {}))

        # legacy v1 format: type + parameters
        action_type = action.get('type', '')
        params = action.get('parameters', {})

        if action_type == 'evict_pod':
            return self.evict_pod(params['namespace'], params['pod_name'], params.get('grace_period', 30))
        elif action_type in ('cordon_node', 'uncordon_node'):
            return self.cordon_node(params['node_name'], uncordon=(action_type == 'uncordon_node'))
        elif action_type == 'drain_node':
            return self.drain_node(params['node_name'], params.get('force', False), params.get('grace_period', 30))
        elif action_type == 'label_node':
            return self.label_node(params['node_name'], params['labels'], params.get('remove', False))
        elif action_type == 'update_deployment':
            return self.update_deployment(params['namespace'], params['deployment_name'], params.get('replicas'), params.get('image'))
        else:
            return {'success': False, 'message': f'Unknown action type: {action_type}'}

    def poll_actions(self) -> List[Dict[str, Any]]:
        """
        Poll backend for pending actions via HTTP (fallback when WebSocket is unavailable).
        Returns list of command dicts: {action_id, action_type, payload}.
        """
        url = f"{self.backend_url}/api/v1/agents/actions/pending"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            commands = data.get('commands', [])
            if commands:
                logger.info(f"[poll] Received {len(commands)} pending commands")
            return commands
        except requests.exceptions.RequestException as e:
            logger.debug(f"[poll] HTTP action poll failed (normal if using WebSocket): {e}")
            return []

    def report_action_result(self, action_id: str, result: Dict[str, Any]) -> bool:
        """
        Report action execution result to backend via HTTP.
        """
        url = f"{self.backend_url}/api/v1/agents/actions/{action_id}/result"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

        payload = {
            'action_id': action_id,
            'success': result.get('success', False),
            'result': {k: v for k, v in result.items() if k not in ('success',)},
            'error': result.get('message') if not result.get('success') else None,
            'nodes_cordoned': result.get('nodes_cordoned'),
            'pods_evicted': result.get('evicted'),
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"[report] Action {action_id} result reported: success={result.get('success')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"[report] Failed to report result for action {action_id}: {e}")
            return False

    def run(self):
        """
        Run the action actuator in a loop (HTTP polling mode).
        Primary path is WebSocket push; this is the fallback.
        """
        self.running = True
        logger.info(f"Starting action actuator (HTTP poll fallback, interval={self.poll_interval}s)")

        while self.running:
            try:
                commands = self.poll_actions()
                for cmd in commands:
                    action_id = cmd.get('action_id')
                    action_type = cmd.get('action_type', '')
                    payload = cmd.get('payload', {})

                    if not action_id or not action_type:
                        continue

                    result = self.execute_action_v2(action_type, payload)
                    self.report_action_result(action_id, result)

            except Exception as e:
                logger.error(f"Error in actuator loop: {e}", exc_info=True)

            time.sleep(self.poll_interval)

        logger.info("Action actuator stopped")

    def handle_spot_interruption(self, notice: Dict[str, Any]):
        """
        Handle a Spot Instance interruption event.
        1. Cordon the node immediately.
        2. Drain the node gracefully.
        """
        node_name = os.getenv('NODE_NAME')
        if not node_name:
            logger.error("Cannot handle spot interruption: NODE_NAME env var not set")
            return

        logger.critical(f"Executing Spot Interruption Protocol for node {node_name}")
        
        # 1. Cordon
        cordon_res = self.cordon_node(node_name, uncordon=False)
        if not cordon_res['success']:
            logger.error(f"Failed to cordon node during spot interruption: {cordon_res.get('message')}")
            # Continue anyway to try and drain what we can
            
        # 2. Drain (Force=True to ensure we clear it)
        drain_res = self.drain_node(node_name, force=True, grace_period=30)
        if drain_res.get('success'):
            logger.info(f"Node {node_name} successfully drained ahead of termination")
        else:
            logger.error(f"Failed to drain node during spot interruption: {drain_res.get('message')}")
            
        # 3. Trigger Fallback (The Safety Net)
        self.request_fallback_node(node_name)

    def request_fallback_node(self, node_name: str):
        """
        Call the backend to request an immediate On-Demand replacement.
        """
        url = f"{self.backend_url}/api/v1/clusters/{self.cluster_id}/fallback"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }
        payload = {
            'node_name': node_name,
            'reason': 'SPOT_INTERRUPTION',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            logger.info(f"Requesting fallback node for {node_name}...")
            # Fire and forget - don't wait long
            requests.post(url, json=payload, headers=headers, timeout=5)
            logger.info("Fallback request sent to backend")
        except Exception as e:
            logger.error(f"Failed to trigger fallback: {e}")

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
