"""
[ARCH-003] PDB-Aware Safe Node Draining

Checks Pod Disruption Budgets before draining nodes to ensure zero-downtime.
Implements safe node evacuation with PDB compliance.
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


@dataclass
class DrainResult:
    """Result of node drain operation"""
    success: bool
    message: str
    pods_evacuated: int
    pods_failed: int
    pdb_violations: List[str]
    duration_seconds: float


class PDBAwaredDrainer:
    """
    Safe node draining with Pod Disruption Budget awareness

    Ensures:
    - PDB constraints are respected
    - No disruptions exceed allowed limits
    - Gradual pod evacuation
    - Zero-downtime guarantee
    """

    def __init__(self, k8s_client: Optional[client.CoreV1Api] = None):
        """
        Initialize PDB-aware drainer

        Args:
            k8s_client: Kubernetes API client (optional, will create if not provided)
        """
        self.core_v1 = k8s_client or client.CoreV1Api()
        self.policy_v1 = client.PolicyV1Api()

    def check_pdb_compliance(self, namespace: str, pod_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if pod can be disrupted without violating PDB

        Args:
            namespace: Pod namespace
            pod_name: Pod name

        Returns:
            Tuple of (can_disrupt, reason)
        """
        try:
            # Get pod
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)

            # Get pod labels
            pod_labels = pod.metadata.labels or {}

            # List all PDBs in namespace
            pdbs = self.policy_v1.list_namespaced_pod_disruption_budget(namespace)

            for pdb in pdbs.items:
                # Check if PDB selector matches pod
                selector = pdb.spec.selector
                if not selector or not selector.match_labels:
                    continue

                # Check if pod matches PDB selector
                if self._pod_matches_selector(pod_labels, selector.match_labels):
                    # Check current disruptions allowed
                    status = pdb.status

                    if status.disruptions_allowed == 0:
                        return False, f"PDB '{pdb.metadata.name}' does not allow disruptions (allowed: 0)"

                    if status.current_healthy < status.desired_healthy:
                        return False, f"PDB '{pdb.metadata.name}' minimum healthy pods not met"

                    logger.info(f"✓ PDB '{pdb.metadata.name}' allows disruption (allowed: {status.disruptions_allowed})")

            return True, None

        except ApiException as e:
            logger.error(f"Failed to check PDB compliance: {e}")
            return False, f"API error: {e.reason}"

    def _pod_matches_selector(self, pod_labels: Dict[str, str], selector_labels: Dict[str, str]) -> bool:
        """Check if pod labels match PDB selector"""
        for key, value in selector_labels.items():
            if pod_labels.get(key) != value:
                return False
        return True

    def can_drain_node(self, node_name: str) -> Tuple[bool, List[str]]:
        """
        Check if node can be drained without violating any PDBs

        Args:
            node_name: Node to check

        Returns:
            Tuple of (can_drain, violations)
        """
        violations = []

        try:
            # Get all pods on node
            pods = self.core_v1.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            )

            logger.info(f"Checking {len(pods.items)} pods on node {node_name}")

            # Check each pod against PDBs
            for pod in pods.items:
                # Skip system pods
                if pod.metadata.namespace in ['kube-system', 'kube-public']:
                    continue

                # Skip completed pods
                if pod.status.phase in ['Succeeded', 'Failed']:
                    continue

                # Check PDB compliance
                can_disrupt, reason = self.check_pdb_compliance(
                    pod.metadata.namespace,
                    pod.metadata.name
                )

                if not can_disrupt:
                    violation = f"{pod.metadata.namespace}/{pod.metadata.name}: {reason}"
                    violations.append(violation)
                    logger.warning(f"❌ Cannot disrupt: {violation}")

            can_drain = len(violations) == 0

            if can_drain:
                logger.info(f"✓ Node {node_name} can be safely drained")
            else:
                logger.warning(f"⚠️ Node {node_name} has {len(violations)} PDB violations")

            return can_drain, violations

        except ApiException as e:
            logger.error(f"Failed to check node drain safety: {e}")
            return False, [f"API error: {e.reason}"]

    def drain_node_safe(self, node_name: str, grace_period_seconds: int = 30, timeout_seconds: int = 300) -> DrainResult:
        """
        Safely drain node with PDB compliance

        Args:
            node_name: Node to drain
            grace_period_seconds: Grace period for pod termination
            timeout_seconds: Maximum time to wait for drain

        Returns:
            DrainResult with operation details
        """
        import time
        start_time = time.time()

        logger.info(f"🔄 Starting safe drain for node: {node_name}")

        # Step 1: Check if node can be drained
        can_drain, violations = self.can_drain_node(node_name)

        if not can_drain:
            return DrainResult(
                success=False,
                message=f"Cannot drain node: {len(violations)} PDB violations",
                pods_evacuated=0,
                pods_failed=0,
                pdb_violations=violations,
                duration_seconds=time.time() - start_time
            )

        # Step 2: Cordon node (prevent new pods)
        try:
            self._cordon_node(node_name)
            logger.info(f"✓ Node {node_name} cordoned")
        except Exception as e:
            return DrainResult(
                success=False,
                message=f"Failed to cordon node: {e}",
                pods_evacuated=0,
                pods_failed=0,
                pdb_violations=[],
                duration_seconds=time.time() - start_time
            )

        # Step 3: Get pods to evict
        try:
            pods = self.core_v1.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            )

            pods_to_evict = [
                pod for pod in pods.items
                if pod.metadata.namespace not in ['kube-system', 'kube-public']
                and pod.status.phase not in ['Succeeded', 'Failed']
            ]

            logger.info(f"Found {len(pods_to_evict)} pods to evict")

        except Exception as e:
            return DrainResult(
                success=False,
                message=f"Failed to list pods: {e}",
                pods_evacuated=0,
                pods_failed=0,
                pdb_violations=[],
                duration_seconds=time.time() - start_time
            )

        # Step 4: Evict pods gradually
        pods_evacuated = 0
        pods_failed = 0

        for pod in pods_to_evict:
            try:
                # Re-check PDB before each eviction
                can_disrupt, reason = self.check_pdb_compliance(
                    pod.metadata.namespace,
                    pod.metadata.name
                )

                if not can_disrupt:
                    logger.warning(f"⚠️ Skipping {pod.metadata.name}: {reason}")
                    pods_failed += 1
                    continue

                # Evict pod
                self._evict_pod(
                    pod.metadata.name,
                    pod.metadata.namespace,
                    grace_period_seconds
                )

                pods_evacuated += 1
                logger.info(f"✓ Evicted {pod.metadata.namespace}/{pod.metadata.name}")

                # Brief pause between evictions
                time.sleep(1)

            except Exception as e:
                logger.error(f"Failed to evict {pod.metadata.name}: {e}")
                pods_failed += 1

        # Step 5: Wait for pods to terminate
        self._wait_for_pods_termination(node_name, timeout_seconds)

        duration = time.time() - start_time

        success = pods_failed == 0

        return DrainResult(
            success=success,
            message=f"Drained {pods_evacuated} pods, {pods_failed} failed",
            pods_evacuated=pods_evacuated,
            pods_failed=pods_failed,
            pdb_violations=[],
            duration_seconds=duration
        )

    def _cordon_node(self, node_name: str):
        """Mark node as unschedulable"""
        body = {
            "spec": {
                "unschedulable": True
            }
        }
        self.core_v1.patch_node(node_name, body)

    def _evict_pod(self, pod_name: str, namespace: str, grace_period_seconds: int):
        """Evict pod using eviction API"""
        eviction = client.V1Eviction(
            metadata=client.V1ObjectMeta(name=pod_name, namespace=namespace),
            delete_options=client.V1DeleteOptions(grace_period_seconds=grace_period_seconds)
        )

        self.core_v1.create_namespaced_pod_eviction(
            pod_name,
            namespace,
            body=eviction
        )

    def _wait_for_pods_termination(self, node_name: str, timeout_seconds: int):
        """Wait for all pods on node to terminate"""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            pods = self.core_v1.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            )

            running_pods = [
                pod for pod in pods.items
                if pod.status.phase not in ['Succeeded', 'Failed']
            ]

            if len(running_pods) == 0:
                logger.info(f"✓ All pods terminated on {node_name}")
                return

            logger.info(f"Waiting for {len(running_pods)} pods to terminate...")
            time.sleep(5)

        logger.warning(f"⚠️ Timeout waiting for pods to terminate on {node_name}")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    from kubernetes import config

    # Load Kubernetes config
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()

    drainer = PDBAwaredDrainer()

    # Test drain
    node_name = "example-node"
    can_drain, violations = drainer.can_drain_node(node_name)

    if can_drain:
        print(f"✓ Node {node_name} can be safely drained")
        # result = drainer.drain_node_safe(node_name)
        # print(f"Drain result: {result}")
    else:
        print(f"❌ Cannot drain node: {len(violations)} violations")
        for violation in violations:
            print(f"  - {violation}")
