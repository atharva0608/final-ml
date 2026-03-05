"""
Step 3 (Execution): Kubernetes Actuator — Agent-Side K8s Operations
======================================================================
Source: agent/actuator.py

PURPOSE
-------
The Kubernetes Actuator runs INSIDE the Kubernetes cluster as part of the
DaemonSet agent. It receives commands from the backend (via WebSocket or
HTTP polling) and executes them using the in-cluster Kubernetes API.

RUNS IN: EKS cluster (not backend server)
PROCESS: agent/main.py → websocket_client.py → actuator.py

KEY OPERATIONS
---------------

  cordon_node(node_name)
  -------------------------
  Marks a node as unschedulable: spec.unschedulable = True
  Effect: New pods will NOT be scheduled on this node.
          Existing pods continue running (not evicted by cordon alone).
  K8s API: PATCH /api/v1/nodes/{name}
  Use case: Prepare node for drain before migration.

  drain_node(node_name, force=False, grace_period=30)
  -----------------------------------------------------
  Gracefully evicts all eligible pods from the node.
  Equivalent to: kubectl drain <node> --ignore-daemonsets --grace-period=30

  Pod eviction order:
    1. Skip DaemonSet pods (they can't move to another node)
    2. Skip mirror pods (static pods managed by kubelet)
    3. If force=False: skip pods not managed by a controller
    4. Check PodDisruptionBudget (PDB):
       - If PDB allows: evict via K8s Eviction API
       - If PDB blocks: retry 5 times with 10s delay
       - If force=True and PDB blocks: force-delete pod (kubectl drain --disable-eviction)
    5. Evict remaining pods with graceful period

  K8s API: POST /api/v1/namespaces/{ns}/pods/{name}/eviction
  Use case: Empty a node before EC2 termination for migration.

  evict_pod(namespace, pod_name, grace_period=30)
  -------------------------------------------------
  Evict a single pod. Respects PDB (retries on 429 PDB violation).
  K8s API: POST /api/v1/namespaces/{ns}/pods/{name}/eviction

  label_node(node_name, labels, remove=False)
  ---------------------------------------------
  Add or remove labels from a node.
  Use case: Mark nodes for Karpenter NodePool selection,
            or label spot/on-demand for workload placement.

  update_deployment(namespace, deployment_name, replicas, image)
  ---------------------------------------------------------------
  Update a deployment's replica count or container image.
  Use case: Scale to 0 during hibernation, update image for rolling restart.

NODE NAME RESOLUTION (critical for CORDON/DRAIN)
-------------------------------------------------
The backend stores EC2 instance IDs, not K8s node names.
The actuator resolves the K8s node name using TWO methods:

  Method 1 (preferred): spec.providerID
    Every EKS node has providerID = "aws://ap-south-1a/i-0abc123"
    Scan all nodes, find one where instance_id appears in providerID.
    Code: _find_node_by_instance_id()

  Method 2 (fallback): Label selector
    Nodes have labels: node.kubernetes.io/instance-type=m5.large
                       topology.kubernetes.io/zone=ap-south-1a
    Query by these labels if Method 1 fails.
    Code: _find_node_name()

PDB (PodDisruptionBudget) HANDLING
------------------------------------
PDB is a Kubernetes policy that prevents too many pods from being evicted
simultaneously (e.g., "at least 2 replicas must be running at all times").

When eviction returns 429 (Too Many Requests = PDB violation):
  - Wait 10 seconds, retry up to 5 times
  - If force=True: bypass PDB by force-deleting the pod (0 grace period)
  - This is equivalent to: kubectl drain --disable-eviction --force

Force deletion is acceptable for STATELESS pods (no data loss risk).
The Pod's controller (Deployment, ReplicaSet) will immediately create a
replacement pod on another node.

AUTHENTICATION
---------------
The actuator runs with in-cluster kubeconfig (automatically available
to pods running in the cluster with appropriate ServiceAccount permissions).
The ServiceAccount used by the Spot Optimizer agent has ClusterRole:
  - pods: get, list, delete, create
  - nodes: get, list, patch
  - evictions: create
  - deployments: get, list, patch, update
"""

# ---------------------------------------------------------------------------
# NODE CLASSIFICATION HELPERS (internal to actuator)
# ---------------------------------------------------------------------------

def is_daemonset_pod(pod) -> bool:
    """
    Check if a pod is managed by a DaemonSet (cannot be evicted/moved).

    DaemonSet pods run on every node and are recreated automatically if deleted.
    They don't need to be evicted during drain — kubectl drain skips them too.

    Args:
        pod: kubernetes.client.V1Pod object

    Returns:
        True if pod is a DaemonSet pod
    """
    if pod.metadata.owner_references:
        for ref in pod.metadata.owner_references:
            if ref.kind == "DaemonSet":
                return True
    return False


def is_mirror_pod(pod) -> bool:
    """
    Check if a pod is a mirror pod (static pod managed by kubelet).

    Mirror pods are created for static pod manifests in /etc/kubernetes/manifests/.
    They cannot be evicted via the K8s API — kubelet manages them directly.

    Args:
        pod: kubernetes.client.V1Pod object

    Returns:
        True if pod is a mirror pod
    """
    return (
        pod.metadata.annotations is not None
        and "kubernetes.io/config.mirror" in pod.metadata.annotations
    )


def has_controller(pod) -> bool:
    """
    Check if a pod is managed by a K8s controller (Deployment, ReplicaSet, Job, etc.).

    Unmanaged pods (no ownerReferences) cannot be evicted unless force=True,
    because they won't be recreated after eviction (data loss risk).

    Args:
        pod: kubernetes.client.V1Pod object

    Returns:
        True if pod has a controller (safe to evict)
    """
    return pod.metadata.owner_references is not None and len(pod.metadata.owner_references) > 0


# ---------------------------------------------------------------------------
# ACTUATOR CONFIGURATION
# ---------------------------------------------------------------------------

# Default eviction settings
EVICTION_RETRY_COUNT = 5       # Retry count for PDB-blocked evictions
EVICTION_RETRY_DELAY = 10      # Seconds between eviction retries
DEFAULT_GRACE_PERIOD = 30      # Default pod eviction grace period (seconds)

# Drain settings
DRAIN_MAX_WAIT_SECONDS = 300   # Maximum wait time for drain to complete

# Node resolution
INSTANCE_TYPE_LABEL = "node.kubernetes.io/instance-type"
AZ_LABEL = "topology.kubernetes.io/zone"
PROVIDER_ID_PREFIX = "aws://"


# ---------------------------------------------------------------------------
# ACTUATOR PSEUDOCODE / REFERENCE IMPLEMENTATION
# ---------------------------------------------------------------------------
# The actual implementation is in agent/actuator.py (class ActionActuator).
# This file provides documented reference implementations for educational purposes.

def resolve_node_name_from_instance_id(k8s_core_v1, instance_id: str):
    """
    Find the K8s node name for a given EC2 instance ID.

    Uses spec.providerID which EKS automatically sets on each node:
      providerID = "aws://ap-south-1a/i-0abc123def456789"

    This is the most reliable method — it works for ALL nodes (EKS-managed,
    Karpenter-provisioned, self-managed), regardless of instance type or label.

    Args:
        k8s_core_v1: kubernetes.client.CoreV1Api() instance
        instance_id: EC2 instance ID (may be truncated to 20 chars in DB)

    Returns:
        K8s node name string, or None if not found

    Example:
        instance_id = "i-0abc123def456789"
        → scans nodes, finds one where providerID contains this string
        → returns "ip-10-0-1-100.ap-south-1.compute.internal"
    """
    if not instance_id:
        return None
    try:
        nodes = k8s_core_v1.list_node()
        for node in nodes.items:
            provider_id = getattr(node.spec, "provider_id", "") or ""
            if instance_id in provider_id:
                return node.metadata.name
    except Exception:
        pass
    return None


def resolve_node_name_from_labels(k8s_core_v1, instance_type: str, az: str):
    """
    Find K8s node name by instance type + AZ labels (fallback method).

    Karpenter-provisioned nodes get standard K8s labels:
      node.kubernetes.io/instance-type=m5.large
      topology.kubernetes.io/zone=ap-south-1a

    Use when instance_id lookup fails (e.g., truncated ID doesn't match).

    Args:
        k8s_core_v1:   kubernetes.client.CoreV1Api() instance
        instance_type: EC2 instance type (e.g. "m5.large")
        az:            Availability zone (e.g. "ap-south-1a")

    Returns:
        K8s node name string, or None if not found
    """
    try:
        label_sel = f"{INSTANCE_TYPE_LABEL}={instance_type}"
        nodes = k8s_core_v1.list_node(label_selector=label_sel)
        for node in nodes.items:
            node_az = (node.metadata.labels or {}).get(AZ_LABEL, "")
            if not az or node_az == az:
                return node.metadata.name
    except Exception:
        pass
    return None


def drain_node_reference(node_name: str, k8s_core_v1, k8s_policy_v1,
                          force: bool = False, grace_period: int = 30) -> dict:
    """
    Reference implementation of the drain_node operation.

    This shows the LOGIC of drain — the actual code is in agent/actuator.py.

    Drain sequence:
      1. Cordon node (mark unschedulable)
      2. List all pods on node
      3. For each pod:
         a. Skip daemonset pods
         b. Skip mirror pods
         c. If not force and no controller: skip (warn)
         d. Check PDB:
            - If force: delete pod directly (bypasses PDB)
            - If not force: evict via Eviction API (respects PDB)
         e. Retry on 429 (PDB blocking) up to EVICTION_RETRY_COUNT times
      4. Return success/failure summary

    Args:
        node_name:    K8s node name
        k8s_core_v1: CoreV1Api instance
        k8s_policy_v1: PolicyV1Api instance
        force:        If True, force-delete PDB-protected pods
        grace_period: Seconds for graceful pod shutdown

    Returns:
        {"success": bool, "evicted": int, "failed": int, "errors": list}
    """
    # Step 1: Cordon the node
    # PATCH /api/v1/nodes/{node_name} → spec.unschedulable = True
    cordon_result = f"Cordon {node_name}"

    # Step 2: List pods on this node
    # GET /api/v1/pods?fieldSelector=spec.nodeName={node_name}
    pods_on_node = []  # would be: k8s_core_v1.list_pod_for_all_namespaces(field_selector=...)

    evicted = 0
    failed = 0
    errors = []

    for pod in pods_on_node:
        # Skip system pods that can't move
        if is_daemonset_pod(pod) or is_mirror_pod(pod):
            continue

        # Skip unmanaged pods unless force=True
        if not force and not has_controller(pod):
            errors.append(f"Pod {pod.metadata.name} not managed by controller (use force=True)")
            failed += 1
            continue

        # PDB check + eviction
        # POST /api/v1/namespaces/{ns}/pods/{name}/eviction
        # → 200 = success, 429 = PDB violation, retry
        evicted += 1

    return {
        "success": failed == 0,
        "evicted": evicted,
        "failed": failed,
        "errors": errors
    }
