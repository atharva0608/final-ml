"""
Step 4 (Execution): Karpenter Controller — NodePool Management
===============================================================
Source: agent/actuator.py (patch_karpenter_nodepool, install_karpenter, etc.)
Related: backend/services/karpenter_service.py

PURPOSE
-------
Control Karpenter's node provisioning by patching its Custom Resource Definitions
(CRDs). Karpenter is a Kubernetes node autoscaler that provisions EC2 instances
in response to pending pods — the Spot Optimizer directs WHICH instances to use.

KARPENTER ARCHITECTURE
------------------------
Karpenter uses two CRDs to know what nodes to provision:

  EC2NodeClass (AWS-specific)
  ----------------------------
  Defines the EC2 configuration for new nodes:
    - AMI (Amazon Machine Image) — which OS/K8s version
    - IAM Role — which role new nodes assume (must join EKS cluster)
    - Subnets — which subnets to launch in (must have karpenter.sh/discovery tag)
    - Security Groups — which SGs to attach (must have karpenter.sh/discovery tag)

  NodePool (Kubernetes-level)
  ----------------------------
  Defines the node constraints Karpenter uses when provisioning:
    - instance_types: ["m5.large", "c5.large"] — allowed instance types
    - capacity_type: ["spot", "on-demand"] — spot preferred, OD fallback
    - architecture: ["amd64", "arm64"] — CPU architecture
    - disruption policy: consolidation, expiry settings

PATCH MECHANISM (how we guide Karpenter)
-----------------------------------------
When the Decision Engine selects a target spot pool (e.g., c5.large in us-east-1b),
we update the NodePool's requirements to prefer that pool:

  BEFORE patch:
    requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot", "on-demand"]
      - key: node.kubernetes.io/instance-type
        operator: In
        values: ["m5.large", "m5.xlarge", "c5.large", "c5.xlarge", ...]

  AFTER patch (target: c5.large in us-east-1b):
    requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot"]               ← spot only
      - key: node.kubernetes.io/instance-type
        operator: In
        values: ["c5.large"]           ← specific type
      - key: topology.kubernetes.io/zone
        operator: In
        values: ["us-east-1b"]         ← specific AZ

When the drained node is terminated and pods become PENDING, Karpenter
provisions a new c5.large spot node in us-east-1b exactly.

PREREQUISITES FOR KARPENTER TO WORK
--------------------------------------
For Karpenter to successfully provision nodes, ALL of these must be in place:

  1. EC2NodeClass
     - spec.role = "KarpenterNodeRole-{cluster_name}"
     - This role must exist in IAM with EKS worker node policies
     - Role must be in aws-auth ConfigMap so new nodes can join cluster

  2. IAM Roles
     - KarpenterNodeRole-{cluster}: EC2 node role (AmazonEKSWorkerNodePolicy, etc.)
     - KarpenterControllerRole-{cluster}: IRSA role for Karpenter controller
       (allows EC2 RunInstances, CreateFleet, SQS, EventBridge, IAM PassRole)
     - OIDC provider must be configured for IRSA to work

  3. Tags on Subnets and Security Groups
     - Tag: karpenter.sh/discovery = {cluster_name}
     - Without this, EC2NodeClass can't find where to launch nodes

  4. Karpenter controller annotation
     - ServiceAccount annotation: eks.amazonaws.com/role-arn = ...KarpenterControllerRole...
     - Without this, Karpenter can't call AWS APIs (no EC2 permissions)

KARPENTER INSTALLATION (via Helm)
-----------------------------------
When a user clicks "Install Karpenter" in the UI:
  1. Backend sends INSTALL_KARPENTER action to agent
  2. Agent runs: helm upgrade --install karpenter oci://... --version 1.0.8
  3. Agent creates default EC2NodeClass + NodePool after install
  4. Backend verifies Karpenter pods are Running

KNOWN LIMITATIONS
------------------
  1. EC2NodeClass.spec.role is IMMUTABLE after creation
     → Cannot patch the role. Must delete + recreate EC2NodeClass.
     → Workaround: remove finalizer, delete, recreate.

  2. AMI alias (al2023@latest) only works with certain K8s + Karpenter versions
     → Karpenter v1.0.8 on K8s 1.32: use specific AMI ID instead of alias
     → Example: ami-01645e472f1746c40

  3. NodePool name must be "default" for Spot Optimizer's auto-rebalancer
     → Custom NodePool names require updating karpenter_service.py defaults
"""

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# NodePool patch payload builder
# ---------------------------------------------------------------------------

def build_nodepool_patch(
    instance_types: List[str],
    capacity_type: List[str] = None,
    az: Optional[str] = None,
    architecture: List[str] = None
) -> dict:
    """
    Build the Kubernetes PATCH body for updating a Karpenter NodePool.

    The Spot Optimizer uses this to tell Karpenter which spot pool to
    provision when pods become PENDING after a node drain.

    Args:
        instance_types:  List of allowed EC2 instance types
                         ["c5.large"] = specific type (targeted migration)
                         ["m5.large", "m6i.large", ...] = multiple options (flexible)
        capacity_type:   ["spot"] = spot only, ["spot", "on-demand"] = spot preferred
        az:              If specified, add AZ requirement (e.g. "us-east-1b")
        architecture:    ["amd64", "arm64"] — CPU architecture requirement

    Returns:
        Dict suitable for CustomObjectsApi.patch_cluster_custom_object()

    Example output:
        {
          "spec": {
            "requirements": [
              {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["spot"]},
              {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": ["c5.large"]},
              {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["us-east-1b"]}
            ]
          }
        }
    """
    if capacity_type is None:
        capacity_type = ["spot"]

    requirements = [
        {
            "key": "karpenter.sh/capacity-type",
            "operator": "In",
            "values": capacity_type
        },
        {
            "key": "node.kubernetes.io/instance-type",
            "operator": "In",
            "values": instance_types
        }
    ]

    if az:
        requirements.append({
            "key": "topology.kubernetes.io/zone",
            "operator": "In",
            "values": [az]
        })

    if architecture:
        requirements.append({
            "key": "kubernetes.io/arch",
            "operator": "In",
            "values": architecture
        })

    return {"spec": {"requirements": requirements}}


def build_default_ec2_node_class(cluster_name: str) -> dict:
    """
    Build the default EC2NodeClass manifest for a cluster.

    Created automatically when Karpenter is installed.
    Uses cluster-specific naming conventions.

    Args:
        cluster_name: EKS cluster name (e.g. "spot-demo-2")

    Returns:
        EC2NodeClass manifest dict for CustomObjectsApi

    IMPORTANT: After Karpenter v1.0+, spec.role is IMMUTABLE.
    If you need to change the IAM role, you must:
      1. Remove finalizer: kubectl patch ec2nodeclass default --type json -p '[{"op":"remove","path":"/metadata/finalizers"}]'
      2. Delete: kubectl delete ec2nodeclass default
      3. Recreate with this function
    """
    return {
        "apiVersion": "karpenter.k8s.aws/v1",
        "kind": "EC2NodeClass",
        "metadata": {"name": "default"},
        "spec": {
            # ⚠️ al2023@latest alias only works on compatible K8s+Karpenter versions
            # For Karpenter 1.0.8 + K8s 1.32, use specific AMI ID:
            # "amiSelectorTerms": [{"id": "ami-01645e472f1746c40"}]
            "amiSelectorTerms": [{"alias": "al2023@latest"}],

            # Must match KarpenterNodeRole-{cluster_name} in IAM
            # This role must have: AmazonEKSWorkerNodePolicy + ECR + CNI + SSM policies
            # AND must be in aws-auth ConfigMap: kubectl edit configmap aws-auth -n kube-system
            "role": f"KarpenterNodeRole-{cluster_name}",

            # Subnets MUST have tag: karpenter.sh/discovery = {cluster_name}
            "subnetSelectorTerms": [
                {"tags": {"karpenter.sh/discovery": cluster_name}}
            ],

            # Security groups MUST have tag: karpenter.sh/discovery = {cluster_name}
            "securityGroupSelectorTerms": [
                {"tags": {"karpenter.sh/discovery": cluster_name}}
            ],
        }
    }


def build_default_node_pool(nodepool_name: str = "default") -> dict:
    """
    Build the default NodePool manifest.

    Created automatically when Karpenter is installed.
    Contains a broad set of instance types — the Spot Optimizer
    narrows this via patch_karpenter_nodepool() during migrations.

    Args:
        nodepool_name: NodePool name (default: "default")

    Returns:
        NodePool manifest dict for CustomObjectsApi
    """
    return {
        "apiVersion": "karpenter.sh/v1",
        "kind": "NodePool",
        "metadata": {"name": nodepool_name},
        "spec": {
            "template": {
                "spec": {
                    "nodeClassRef": {
                        "group": "karpenter.k8s.aws",
                        "kind": "EC2NodeClass",
                        "name": "default"
                    },
                    "requirements": [
                        # Allow both spot and on-demand (spot preferred by Karpenter)
                        {
                            "key": "karpenter.sh/capacity-type",
                            "operator": "In",
                            "values": ["spot", "on-demand"]
                        },
                        # Allow amd64 architecture only (add "arm64" for Graviton)
                        {
                            "key": "kubernetes.io/arch",
                            "operator": "In",
                            "values": ["amd64"]
                        },
                        # Broad instance type set — will be narrowed by Spot Optimizer
                        # to specific types during migration
                        {
                            "key": "node.kubernetes.io/instance-type",
                            "operator": "In",
                            "values": [
                                "m5.large", "m5.xlarge",
                                "m6i.large", "m6i.xlarge",
                                "c5.large", "c5.xlarge",
                                "c6i.large", "c6i.xlarge",
                            ]
                        }
                    ]
                }
            },
            "disruption": {
                # Consolidate nodes when empty OR underutilized
                "consolidationPolicy": "WhenEmptyOrUnderutilized",
                "consolidateAfter": "1m"  # Check consolidation every 1 minute
            }
        }
    }


# ---------------------------------------------------------------------------
# Karpenter status check
# ---------------------------------------------------------------------------

def check_karpenter_ready(k8s_custom_api) -> dict:
    """
    Check if Karpenter's EC2NodeClass and NodePool are READY.

    Called by backend to verify Karpenter is operational after install.
    Returns status for each CRD.

    Args:
        k8s_custom_api: kubernetes.client.CustomObjectsApi() instance

    Returns:
        {
            "ec2_node_class_ready": bool,
            "node_pool_ready": bool,
            "ec2_node_class_conditions": list,
            "node_pool_conditions": list
        }
    """
    result = {
        "ec2_node_class_ready": False,
        "node_pool_ready": False,
        "ec2_node_class_conditions": [],
        "node_pool_conditions": [],
    }

    try:
        nc = k8s_custom_api.get_cluster_custom_object(
            group="karpenter.k8s.aws", version="v1", plural="ec2nodeclasses", name="default"
        )
        conditions = nc.get("status", {}).get("conditions", [])
        result["ec2_node_class_conditions"] = conditions
        result["ec2_node_class_ready"] = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
    except Exception:
        pass

    try:
        np = k8s_custom_api.get_cluster_custom_object(
            group="karpenter.sh", version="v1", plural="nodepools", name="default"
        )
        conditions = np.get("status", {}).get("conditions", [])
        result["node_pool_conditions"] = conditions
        result["node_pool_ready"] = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
    except Exception:
        pass

    return result
