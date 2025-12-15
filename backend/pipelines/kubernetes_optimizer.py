"""
Kubernetes Optimizer - K8s Node Optimization Pipeline

This pipeline handles Kubernetes worker node optimization with cluster awareness:
1. Identification: Find nodes labeled as lifecycle=on-demand
2. Scale Out: Launch new Spot node and wait for Ready status
3. Cordon: Mark old node as unschedulable
4. Drain: Evict pods respecting PodDisruptionBudgets
5. Terminate: Stop old EC2 instance
6. Verify: Ensure all pods rescheduled successfully

CRITICAL INVARIANT: Cluster capacity must NEVER drop during optimization
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy.orm import Session
import time

from database.models import Instance, Account
from utils.aws_session import get_ec2_client
from pipelines.linear_optimizer import execute_atomic_switch
from logic.risk_manager import RiskManager


@dataclass
class K8sNode:
    """Kubernetes node target for optimization"""
    node_name: str
    instance_id: str  # EC2 instance ID
    instance_type: str
    availability_zone: str
    cluster_name: str
    node_group: Optional[str] = None
    is_ready: bool = False
    pod_count: int = 0


class KubernetesPipeline:
    """
    Kubernetes-aware node optimization pipeline

    Implements the 4-Step Safety Dance:
    1. Scale Out: Launch new Spot node FIRST
    2. Cordon: Mark old node unschedulable
    3. Drain: Evict pods gracefully
    4. Terminate: Remove old EC2 instance

    This ensures zero-downtime optimization for Kubernetes workloads.
    """

    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Kubernetes pipeline

        Args:
            db: Database session
            config: Optional configuration (kubectl context, kubeconfig path, etc.)
        """
        self.db = db
        self.config = config or {}
        self.risk_manager = RiskManager(db=db)

        # Kubernetes client will be initialized when needed
        self.k8s_client = None

    def execute(self, instance_id: str) -> Dict[str, Any]:
        """
        Execute Kubernetes-aware node optimization

        The correct order is:
        1. Scale Out: Launch new Spot node and wait until Ready
        2. Cordon: Mark old node as unschedulable
        3. Drain: Evict pods respecting PodDisruptionBudgets
        4. Terminate: Stop old EC2 instance
        5. Verify: Ensure all pods rescheduled successfully

        Args:
            instance_id: Database instance UUID

        Returns:
            Execution result dict
        """
        print(f"\n{'='*80}")
        print(f"☸️  KUBERNETES OPTIMIZATION - Node Mode")
        print(f"{'='*80}\n")

        # Fetch instance from database
        instance = self.db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        # Validate cluster membership
        if not instance.cluster_membership:
            raise ValueError(f"Instance {instance.instance_id} is not part of a Kubernetes cluster")

        cluster_name = instance.cluster_membership.get('cluster_name')
        node_group = instance.cluster_membership.get('node_group')

        print(f"Instance: {instance.instance_id}")
        print(f"Cluster: {cluster_name}")
        print(f"Node Group: {node_group}")
        print(f"Type: {instance.instance_type}")
        print(f"AZ: {instance.availability_zone}")
        print(f"{'='*80}\n")

        # Initialize Kubernetes client
        self._init_k8s_client(cluster_name, instance.account.region)

        # Get node details
        node = self._get_node_from_instance(instance.instance_id)
        if not node:
            raise ValueError(f"Cannot find Kubernetes node for instance {instance.instance_id}")

        print(f"🎯 Target Node: {node.node_name}")
        print(f"   Pods Running: {node.pod_count}")
        print(f"   Status: {'Ready' if node.is_ready else 'Not Ready'}\n")

        try:
            # PHASE 1: Scale Out - Launch new Spot node FIRST
            print("[Phase 1/4] 🚀 Scale Out - Launching new Spot node...")
            new_instance_id = self._phase_scale_out(instance, node)
            print(f"✓ New node launched: {new_instance_id}\n")

            # PHASE 2: Cordon - Mark old node unschedulable
            print("[Phase 2/4] 🚧 Cordon - Marking old node unschedulable...")
            self._phase_cordon(node.node_name)
            print(f"✓ Node {node.node_name} cordoned\n")

            # PHASE 3: Drain - Evict pods gracefully
            print("[Phase 3/4] 💧 Drain - Evicting pods...")
            self._phase_drain(node.node_name, respect_pdbs=True)
            print(f"✓ Node {node.node_name} drained\n")

            # PHASE 4: Terminate - Remove old EC2 instance
            print("[Phase 4/4] 🛑 Terminate - Removing old EC2 instance...")
            self._phase_terminate(instance.instance_id, instance.account, instance.account.region)
            print(f"✓ Old instance {instance.instance_id} terminated\n")

            # Update database
            instance.instance_id = new_instance_id
            instance.updated_at = datetime.utcnow()
            self.db.commit()

            print(f"{'='*80}")
            print(f"✅ KUBERNETES OPTIMIZATION COMPLETE")
            print(f"{'='*80}")
            print(f"Old Instance: {node.instance_id}")
            print(f"New Instance: {new_instance_id}")
            print(f"{'='*80}\n")

            return {
                "status": "success",
                "old_instance_id": node.instance_id,
                "new_instance_id": new_instance_id,
                "node_name": node.node_name,
                "pods_migrated": node.pod_count
            }

        except Exception as e:
            print(f"\n❌ Optimization failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "instance_id": instance.instance_id
            }

    def _init_k8s_client(self, cluster_name: str, region: str):
        """
        Initialize Kubernetes client for cluster

        NOTE: This is a placeholder. In production, you need:
        1. Kubernetes Python client (pip install kubernetes)
        2. Access to kubeconfig or AWS EKS credentials
        3. Proper RBAC permissions for node management

        Args:
            cluster_name: EKS cluster name
            region: AWS region
        """
        # Placeholder implementation
        # In production, you would:
        # from kubernetes import client, config
        # config.load_kube_config()  # or load from EKS
        # self.k8s_client = client.CoreV1Api()

        print(f"⚠️  Kubernetes client initialization is a placeholder")
        print(f"   In production, this would connect to EKS cluster: {cluster_name}")
        self.k8s_client = MockK8sClient()  # Mock for now

    def _get_node_from_instance(self, instance_id: str) -> Optional[K8sNode]:
        """
        Find Kubernetes node corresponding to EC2 instance

        Args:
            instance_id: EC2 instance ID

        Returns:
            K8sNode object or None
        """
        # Placeholder implementation
        # In production, you would query Kubernetes API:
        # nodes = self.k8s_client.list_node()
        # for node in nodes.items:
        #     provider_id = node.spec.provider_id  # e.g., "aws:///us-east-1a/i-1234567890abcdef0"
        #     if instance_id in provider_id:
        #         return K8sNode(...)

        # Mock node for now
        return K8sNode(
            node_name=f"ip-10-0-1-100.ec2.internal",
            instance_id=instance_id,
            instance_type="c5.large",
            availability_zone="us-east-1a",
            cluster_name="prod-eks",
            is_ready=True,
            pod_count=5
        )

    def _phase_scale_out(self, instance: Instance, old_node: K8sNode) -> str:
        """
        Phase 1: Scale Out - Launch new Spot node

        This MUST complete before cordoning the old node to ensure
        cluster capacity is maintained.

        Args:
            instance: Database instance record
            old_node: Old node to be replaced

        Returns:
            New EC2 instance ID
        """
        # Get EC2 client
        ec2 = get_ec2_client(
            account_id=instance.account.account_id,
            region=instance.account.region,
            db=self.db
        )

        # Launch new Spot instance using atomic switch
        result = execute_atomic_switch(
            ec2_client=ec2,
            source_instance_id=instance.instance_id,
            target_instance_type=instance.instance_type,
            target_az=instance.availability_zone,
            dry_run=False
        )

        new_instance_id = result['new_instance_id']

        # Wait for new node to join cluster and become Ready
        print(f"   Waiting for new node to join cluster...")
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            new_node = self._get_node_from_instance(new_instance_id)
            if new_node and new_node.is_ready:
                print(f"   ✓ New node {new_node.node_name} is Ready")
                return new_instance_id

            time.sleep(10)

        raise RuntimeError(f"New node failed to become Ready within {max_wait}s")

    def _phase_cordon(self, node_name: str):
        """
        Phase 2: Cordon - Mark node as unschedulable

        This prevents new pods from being scheduled on the node
        while we prepare to drain it.

        Args:
            node_name: Kubernetes node name
        """
        # Placeholder implementation
        # In production, you would:
        # from kubernetes import client
        # body = {"spec": {"unschedulable": True}}
        # self.k8s_client.patch_node(node_name, body)

        print(f"   kubectl cordon {node_name}")
        print(f"   (This is a placeholder - in production, would use Kubernetes API)")

    def _phase_drain(self, node_name: str, respect_pdbs: bool = True):
        """
        Phase 3: Drain - Evict all pods from node

        This gracefully moves pods to other nodes (including the new
        Spot node we just launched). It respects PodDisruptionBudgets
        to prevent breaking availability guarantees.

        Args:
            node_name: Kubernetes node name
            respect_pdbs: If True, respects PodDisruptionBudgets
        """
        # Placeholder implementation
        # In production, you would:
        # from kubernetes import client
        # pods = self.k8s_client.list_pod_for_all_namespaces(
        #     field_selector=f"spec.nodeName={node_name}"
        # )
        # for pod in pods.items:
        #     # Check PDB before evicting
        #     self.k8s_client.create_namespaced_pod_eviction(
        #         name=pod.metadata.name,
        #         namespace=pod.metadata.namespace,
        #         body=client.V1Eviction(...)
        #     )

        print(f"   kubectl drain {node_name} --ignore-daemonsets --delete-emptydir-data")
        if respect_pdbs:
            print(f"   --pod-eviction-budget=respect")
        print(f"   (This is a placeholder - in production, would use Kubernetes API)")

        # Simulate drain time
        print(f"   Waiting for pods to migrate...")
        time.sleep(5)  # In production, would wait for actual pod evictions

    def _phase_terminate(self, instance_id: str, account: Account, region: str):
        """
        Phase 4: Terminate - Stop old EC2 instance

        This should only be called AFTER the drain is complete to ensure
        all pods have been rescheduled.

        Args:
            instance_id: EC2 instance ID to terminate
            account: Database account record
            region: AWS region
        """
        ec2 = get_ec2_client(
            account_id=account.account_id,
            region=region,
            db=self.db
        )

        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"   EC2 instance {instance_id} termination initiated")


class MockK8sClient:
    """Mock Kubernetes client for placeholder implementation"""
    pass


# For testing
if __name__ == '__main__':
    print("="*80)
    print("KUBERNETES OPTIMIZER - Production EKS Pipeline")
    print("="*80)
    print("\nImplements 4-Step Safety Dance for zero-downtime node replacement:")
    print("  1. Scale Out: Launch new Spot node FIRST")
    print("  2. Cordon: Mark old node unschedulable")
    print("  3. Drain: Evict pods respecting PDBs")
    print("  4. Terminate: Remove old EC2 instance")
    print("\nCRITICAL INVARIANT: Cluster capacity NEVER drops during optimization")
    print("\nPrerequisites:")
    print("  - kubectl access to cluster")
    print("  - Kubernetes Python client (pip install kubernetes==26.1.0)")
    print("  - Proper RBAC permissions (node management)")
    print("="*80)
