"""
Steps 2b–2c: Workload Classifier
==================================
Source: backend/services/workload_inspector.py

PURPOSE
-------
Classify each Kubernetes node into one of three categories:
  - STATELESS_ELIGIBLE: Can be migrated to spot safely (no data loss risk)
  - STATEFUL:           Has persistent state, migrate only with human approval
  - SYSTEM_PROTECTED:   Runs cluster-critical services, never migrate

The Decision Engine requires at least ONE STATELESS_ELIGIBLE node to proceed.
If all nodes are stateful or system-protected, the action is blocked.

WHY NODE CLASSIFICATION MATTERS
---------------------------------
Spot instances can be interrupted with only 2 minutes notice.
  - Stateless pods: can be rescheduled on any other node instantly ✓
  - Stateful pods:  may lose data if interrupted without special handling ✗
  - System pods:    may take down the entire cluster if interrupted ✗✗

Without classification, migrating a stateful DB to spot = potential data loss.
Without classification, migrating CoreDNS to spot = cluster-wide DNS outage.

CLASSIFICATION ALGORITHM
--------------------------

  SYSTEM_PROTECTED (highest priority — checked first):
    - Runs kube-system namespace pods (CoreDNS, kube-proxy, AWS VPC CNI)
    - Runs monitoring stack (prometheus, grafana, datadog)
    - Runs Karpenter controller itself
    - Node label: node-role.kubernetes.io/control-plane=true

  STATEFUL (checked second):
    - Runs StatefulSet pods (databases, message queues, stateful apps)
    - Has PersistentVolumeClaim (PVC) attached
    - Owner reference kind == "StatefulSet"
    - Annotation: spot-optimizer/stateful=true

  STATELESS_ELIGIBLE (default if neither above):
    - Runs only Deployment, ReplicaSet, or Job pods
    - No PVC attachments
    - Can be safely drained and rescheduled

CACHING STRATEGY
-----------------
Classification is expensive (requires Kubernetes API calls for each pod).
Results are cached in Redis for 5 minutes per cluster:
  Key:   spot:workload:classification:{cluster_id}
  TTL:   5 minutes
  Value: JSON {"node-name": "STATELESS_ELIGIBLE", ...}

If classification is stale or missing, the Decision Engine returns early
with reason "Node classification unavailable — WorkloadInspector scan required".
"""

from enum import Enum
from typing import Dict, Optional, List
import json


# ---------------------------------------------------------------------------
# Node Status Enum
# ---------------------------------------------------------------------------

class NodeStatus(str, Enum):
    """
    Classification result for a Kubernetes node.

    These values are stored in Redis and compared by DecisionEngine Step 2c.
    String values match what's stored in Redis for easy serialization.
    """
    STATELESS_ELIGIBLE = "STATELESS_ELIGIBLE"  # Safe to migrate to spot
    STATEFUL = "STATEFUL"                       # Has persistent state, manual-only
    SYSTEM_PROTECTED = "SYSTEM_PROTECTED"       # Critical cluster services, never migrate


# ---------------------------------------------------------------------------
# System namespace patterns (pods in these namespaces = SYSTEM_PROTECTED)
# ---------------------------------------------------------------------------

SYSTEM_NAMESPACES = {
    "kube-system",      # CoreDNS, kube-proxy, AWS VPC CNI, cluster-autoscaler
    "karpenter",        # Karpenter controller itself
    "monitoring",       # Prometheus, Grafana (common namespace)
    "observability",    # Alternative monitoring namespace
    "cert-manager",     # Certificate management
    "ingress-nginx",    # Ingress controller
    "istio-system",     # Service mesh control plane
    "linkerd",          # Alternative service mesh
    "flux-system",      # GitOps operator
    "argocd",           # ArgoCD GitOps
}

# Labels that mark a node as system/control-plane
SYSTEM_NODE_LABELS = {
    "node-role.kubernetes.io/control-plane": "true",
    "node-role.kubernetes.io/master": "true",
}

# StatefulSet owner kind — pods with this owner are considered stateful
STATEFUL_OWNER_KINDS = {"StatefulSet"}

# Annotation that explicitly marks a node as stateful (user override)
STATEFUL_ANNOTATION = "spot-optimizer/stateful"


# ---------------------------------------------------------------------------
# WorkloadInspector
# ---------------------------------------------------------------------------

class WorkloadInspector:
    """
    Classifies Kubernetes nodes by workload type for safe spot migration.

    Works in two modes:
      1. Live scan: Queries Kubernetes API for current pod distribution
      2. Cache read: Returns cached classification from Redis (faster)

    DecisionEngine always uses mode 2 (cache read). A separate Celery task
    runs live scans every 5 minutes to keep the cache fresh.
    """

    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, redis_client):
        """
        Args:
            redis_client: Redis connection (from backend.core.redis_client)
        """
        self.redis = redis_client

    def get_cached_classification(self, cluster_id: str) -> Optional[Dict[str, NodeStatus]]:
        """
        Read node classification from Redis cache.

        Called by DecisionEngine Step 2b. If the cache is missing or expired,
        returns None and the pipeline blocks with "classification unavailable".

        Args:
            cluster_id: Cluster identifier

        Returns:
            Dict mapping node_name → NodeStatus, or None if cache miss.

        Example return value:
            {
                "ip-10-0-1-100.ap-south-1.compute.internal": NodeStatus.STATELESS_ELIGIBLE,
                "ip-10-0-1-101.ap-south-1.compute.internal": NodeStatus.SYSTEM_PROTECTED,
                "ip-10-0-1-102.ap-south-1.compute.internal": NodeStatus.STATEFUL,
            }
        """
        cache_key = f"spot:workload:classification:{cluster_id}"
        data = self.redis.get(cache_key)

        if not data:
            return None

        # Deserialize from JSON
        try:
            raw = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
            return {node: NodeStatus(status) for node, status in raw.items()}
        except Exception:
            return None

    def store_classification(self, cluster_id: str, classification: Dict[str, NodeStatus]):
        """
        Store classification results in Redis cache.

        Called by the Celery beat task (workload_scanner task) after a
        live Kubernetes API scan. Results expire after 5 minutes.

        Args:
            cluster_id:     Cluster identifier
            classification: Dict mapping node_name → NodeStatus
        """
        cache_key = f"spot:workload:classification:{cluster_id}"
        serialized = json.dumps({node: status.value for node, status in classification.items()})
        self.redis.setex(cache_key, self.CACHE_TTL_SECONDS, serialized)

    def classify_node(
        self,
        node_name: str,
        node_labels: Dict[str, str],
        node_annotations: Dict[str, str],
        pods_on_node: List[dict]
    ) -> NodeStatus:
        """
        Classify a single node based on its labels and running pods.

        This is called during a live scan (not in the decision pipeline hot path).
        The result is stored in Redis and read by get_cached_classification().

        Classification logic (checked in priority order):
          1. SYSTEM_PROTECTED if node has control-plane label
          2. SYSTEM_PROTECTED if any pod runs in a system namespace
          3. STATEFUL if user annotated with spot-optimizer/stateful=true
          4. STATEFUL if any pod is owned by a StatefulSet
          5. STATEFUL if any pod has a PVC mount
          6. STATELESS_ELIGIBLE otherwise (safe to migrate)

        Args:
            node_name:        Kubernetes node name
            node_labels:      Node metadata.labels dict
            node_annotations: Node metadata.annotations dict
            pods_on_node:     List of pod dicts (from K8s API, spec + metadata)

        Returns:
            NodeStatus classification
        """
        # Priority 1: System node label → always protected
        for label_key, label_val in SYSTEM_NODE_LABELS.items():
            if node_labels.get(label_key) == label_val:
                return NodeStatus.SYSTEM_PROTECTED

        # Priority 2: System namespace pods → protected (Karpenter, CoreDNS, etc.)
        for pod in pods_on_node:
            pod_namespace = (pod.get("metadata") or {}).get("namespace", "")
            if pod_namespace in SYSTEM_NAMESPACES:
                return NodeStatus.SYSTEM_PROTECTED

        # Priority 3: User annotation override → stateful
        if node_annotations.get(STATEFUL_ANNOTATION) == "true":
            return NodeStatus.STATEFUL

        # Priority 4: StatefulSet pods → stateful
        for pod in pods_on_node:
            owner_refs = (pod.get("metadata") or {}).get("ownerReferences", [])
            for owner in owner_refs:
                if owner.get("kind") in STATEFUL_OWNER_KINDS:
                    return NodeStatus.STATEFUL

        # Priority 5: PVC mounts → stateful (pod needs persistent disk)
        for pod in pods_on_node:
            volumes = (pod.get("spec") or {}).get("volumes", [])
            for vol in volumes:
                if vol.get("persistentVolumeClaim"):
                    return NodeStatus.STATEFUL

        # Default: stateless, safe to migrate
        return NodeStatus.STATELESS_ELIGIBLE

    def filter_stateless_nodes(
        self, classification: Dict[str, NodeStatus]
    ) -> List[str]:
        """
        Extract only STATELESS_ELIGIBLE node names from classification.

        Called by DecisionEngine Step 2c. These are the nodes that can
        be safely drained and migrated to a different spot pool.

        Args:
            classification: Output from get_cached_classification()

        Returns:
            List of eligible node names (may be empty — pipeline blocks if so)
        """
        return [
            node_name
            for node_name, status in classification.items()
            if status == NodeStatus.STATELESS_ELIGIBLE
        ]
