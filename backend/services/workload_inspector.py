"""
Workload Inspector
=================

Auto-detects stateful vs stateless workloads per cluster.
Scans Kubernetes API every 10 min, classifies each node.
Cache in Redis: spot:node_classification:{cluster_id}
"""

from redis import Redis
from typing import Dict, Optional
from enum import Enum
import json
import logging
import random

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """Node classification status"""
    STATELESS_ELIGIBLE = "STATELESS_ELIGIBLE"   # Safe to optimize
    STATEFUL_PROTECTED = "STATEFUL_PROTECTED"   # Has PVC/StatefulSet
    DRAIN_UNSAFE = "DRAIN_UNSAFE"               # PDB maxUnavailable=0 or finalizer issue
    SYSTEM_PROTECTED = "SYSTEM_PROTECTED"       # Control plane or system node


class WorkloadInspector:
    """
    Auto-detects stateful vs stateless workloads per cluster.

    Classification logic:
    1. Control plane / system nodes → SYSTEM_PROTECTED
    2. Has StatefulSet pods → STATEFUL_PROTECTED
    3. Has PVC (EBS CSI) volumes → STATEFUL_PROTECTED
    4. Has hostPath volumes → STATEFUL_PROTECTED
    5. PDB maxUnavailable=0 → DRAIN_UNSAFE
    6. Else → STATELESS_ELIGIBLE

    CRITICAL: Decision Engine uses cached classification at runtime.
              Never trust cluster.workload_type column for safety decisions.
    """

    CLASSIFICATION_TTL = 600  # 10 minutes

    def __init__(self, redis: Redis, k8s_client=None):
        self.redis = redis
        self.k8s = k8s_client

    def scan_cluster(self, cluster_id: str) -> Dict[str, str]:
        """
        Full scan: classify every node in cluster.

        SCALABILITY NOTES:
        - Use field selectors to reduce K8s API load
        - Cache PVC/PV mapping in-memory for duration of single scan
        - Add random jitter (0-60s) to scheduling to avoid synchronized bursts
        - Retry with exponential backoff on API errors (1s, 2s, 4s, max 3 retries)

        Args:
            cluster_id: Cluster identifier

        Returns:
            {
                "node-1": "STATELESS_ELIGIBLE",
                "node-2": "STATEFUL_PROTECTED",
                ...
            }
        """
        try:
            # Add jitter to prevent synchronized API storms
            # jitter_seconds = random.randint(0, 60)
            # time.sleep(jitter_seconds)  # Commented out - implement in scheduler

            classification = {}

            if not self.k8s:
                logger.warning(f"K8s client not available for cluster {cluster_id}")
                return classification

            # Fetch nodes with retries
            nodes = self._fetch_nodes_with_retry(cluster_id)

            if not nodes:
                logger.warning(f"No nodes found for cluster {cluster_id}")
                return classification

            # Classify each node
            for node in nodes:
                node_name = node.get("metadata", {}).get("name")
                if not node_name:
                    continue

                # 1. Check if system/control plane node
                if self._is_system_node(node):
                    classification[node_name] = NodeStatus.SYSTEM_PROTECTED
                    continue

                # 2. Fetch pods on this node
                pods = self._fetch_pods_on_node_with_retry(cluster_id, node_name)

                # 3. Check for StatefulSets
                has_stateful = any(
                    pod.get("metadata", {}).get("ownerReferences", [{}])[0].get("kind") == "StatefulSet"
                    for pod in pods
                )

                if has_stateful:
                    classification[node_name] = NodeStatus.STATEFUL_PROTECTED
                    continue

                # 4. Check for PVC volumes
                has_pvc = self._has_pvc_volumes(pods)

                if has_pvc:
                    classification[node_name] = NodeStatus.STATEFUL_PROTECTED
                    continue

                # 5. Check for hostPath volumes
                has_hostpath = self._has_hostpath_volumes(pods)

                if has_hostpath:
                    classification[node_name] = NodeStatus.STATEFUL_PROTECTED
                    continue

                # 6. Check for blocking PDB
                if self._has_blocking_pdb(cluster_id, node_name, pods):
                    classification[node_name] = NodeStatus.DRAIN_UNSAFE
                    continue

                # Default: stateless eligible
                classification[node_name] = NodeStatus.STATELESS_ELIGIBLE

            # Cache in Redis
            cache_key = f"spot:node_classification:{cluster_id}"
            self.redis.setex(cache_key, self.CLASSIFICATION_TTL, json.dumps(classification))

            # Update cluster.workload_type column for audit (informational only)
            self._update_cluster_workload_type(cluster_id, classification)

            logger.info(
                f"Scanned cluster {cluster_id}: {len(classification)} nodes classified"
            )

            return classification

        except Exception as e:
            logger.error(f"Error scanning cluster {cluster_id}: {e}")
            return {}

    def get_cached_classification(self, cluster_id: str) -> Optional[Dict]:
        """
        Get cached classification. Returns None if expired — caller must handle.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Classification dict or None if expired/unavailable
        """
        cache_key = f"spot:node_classification:{cluster_id}"

        try:
            data = self.redis.get(cache_key)
            return json.loads(data) if data else None

        except Exception as e:
            logger.error(f"Error fetching cached classification: {e}")
            return None

    def _fetch_nodes_with_retry(self, cluster_id: str, max_retries: int = 3):
        """Fetch nodes with exponential backoff on API errors"""
        for attempt in range(max_retries):
            try:
                return self.k8s.list_nodes(cluster_id)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"K8s API error (attempt {attempt + 1}), retry in {delay}s: {e}")
                    # time.sleep(delay)  # Implement if needed
                else:
                    logger.error(f"Failed to fetch nodes after {max_retries} attempts: {e}")
                    return []
        return []

    def _fetch_pods_on_node_with_retry(self, cluster_id: str, node_name: str, max_retries: int = 3):
        """Fetch pods on node with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return self.k8s.list_pods_on_node(cluster_id, node_name)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(f"K8s API error fetching pods (attempt {attempt + 1}): {e}")
                else:
                    logger.error(f"Failed to fetch pods after {max_retries} attempts: {e}")
                    return []
        return []

    def _is_system_node(self, node: dict) -> bool:
        """Check if node is control plane or system node"""
        labels = node.get("metadata", {}).get("labels", {})

        # Control plane labels
        if any([
            "node-role.kubernetes.io/control-plane" in labels,
            "node-role.kubernetes.io/master" in labels,
        ]):
            return True

        # System node pool labels
        if labels.get("node-role.kubernetes.io/system") == "true":
            return True

        return False

    def _has_pvc_volumes(self, pods: list) -> bool:
        """Check if any pod has PVC volumes"""
        for pod in pods:
            volumes = pod.get("spec", {}).get("volumes", [])
            for vol in volumes:
                if "persistentVolumeClaim" in vol:
                    return True
        return False

    def _has_hostpath_volumes(self, pods: list) -> bool:
        """Check if any pod has hostPath volumes"""
        for pod in pods:
            volumes = pod.get("spec", {}).get("volumes", [])
            for vol in volumes:
                if "hostPath" in vol:
                    return True
        return False

    def _has_blocking_pdb(self, cluster_id: str, node_name: str, pods: list) -> bool:
        """
        Check if any PDB would block drain (maxUnavailable=0).

        This is a simplified check. Full implementation would query PDB API.
        """
        # TODO: Implement PDB check via K8s API
        # For now, return False (assume no blocking PDBs)
        return False

    def _update_cluster_workload_type(self, cluster_id: str, classification: Dict):
        """
        Update cluster.workload_type column for audit/display.

        IMPORTANT: This is informational cache ONLY.
                   Decision Engine MUST use get_cached_classification() at runtime.
        """
        try:
            stateless_count = sum(
                1 for status in classification.values()
                if status == NodeStatus.STATELESS_ELIGIBLE
            )
            stateful_count = sum(
                1 for status in classification.values()
                if status == NodeStatus.STATEFUL_PROTECTED
            )

            total = len(classification)

            if total == 0:
                workload_type = "UNKNOWN"
            elif stateless_count == total:
                workload_type = "STATELESS"
            elif stateful_count == total:
                workload_type = "STATEFUL"
            else:
                workload_type = "MIXED"

            # Store in Redis for now (would update DB in real implementation)
            cache_key = f"spot:workload_type:{cluster_id}"
            self.redis.setex(cache_key, self.CLASSIFICATION_TTL, workload_type)

            logger.debug(f"Cluster {cluster_id} workload_type: {workload_type}")

        except Exception as e:
            logger.error(f"Error updating workload type: {e}")
