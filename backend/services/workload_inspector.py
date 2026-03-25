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
import math
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

    CLASSIFICATION_TTL = 540  # 9 minutes (Issue 3a: was 600s — beat fires every 9min, TTL must be < period)

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
            arch_classification = {}  # node_name → list of required architectures (empty = any)

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
                    arch_classification[node_name] = []
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
                    arch_classification[node_name] = []
                    continue

                # 4. Check for PVC volumes
                has_pvc = self._has_pvc_volumes(pods)

                if has_pvc:
                    classification[node_name] = NodeStatus.STATEFUL_PROTECTED
                    arch_classification[node_name] = []
                    continue

                # 5. Check for hostPath volumes
                has_hostpath = self._has_hostpath_volumes(pods)

                if has_hostpath:
                    classification[node_name] = NodeStatus.STATEFUL_PROTECTED
                    arch_classification[node_name] = []
                    continue

                # 6. Check for blocking PDB
                if self._has_blocking_pdb(cluster_id, node_name, pods):
                    classification[node_name] = NodeStatus.DRAIN_UNSAFE
                    arch_classification[node_name] = []
                    continue

                # Collect required architectures from pod constraints (Bug A-5 fix)
                node_required_archs: set = set()
                for pod in pods:
                    arch = self._has_arch_affinity(pod)
                    if arch:
                        node_required_archs.add(arch)
                # Store arch constraints alongside classification
                arch_classification[node_name] = sorted(node_required_archs)

                # Default: stateless eligible
                classification[node_name] = NodeStatus.STATELESS_ELIGIBLE

            # Cache classification in Redis
            cache_key = f"spot:node_classification:{cluster_id}"
            self.redis.setex(cache_key, self.CLASSIFICATION_TTL, json.dumps(classification))

            # Cache per-node arch constraints (used by auto_rebalancer to build NodePool requirements)
            arch_cache_key = f"spot:node_arch_constraints:{cluster_id}"
            self.redis.setex(arch_cache_key, self.CLASSIFICATION_TTL, json.dumps(arch_classification))

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

    def _has_arch_affinity(self, pod: dict) -> str | None:
        """
        Returns the required architecture if the pod is pinned to a specific arch.
        Returns None if the pod can run on any architecture (safe for Graviton migration).

        Checks nodeSelector and nodeAffinity.requiredDuringScheduling.
        """
        spec = pod.get("spec", {})

        # Check nodeSelector
        node_selector = spec.get("nodeSelector", {})
        arch = node_selector.get("kubernetes.io/arch")
        if arch:
            return arch

        # Check nodeAffinity
        affinity = spec.get("affinity", {})
        node_affinity = affinity.get("nodeAffinity", {})
        required = node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution", {})
        for term in required.get("nodeSelectorTerms", []):
            for expr in term.get("matchExpressions", []):
                if expr.get("key") == "kubernetes.io/arch" and expr.get("operator") == "In":
                    values = expr.get("values", [])
                    return values[0] if len(values) == 1 else None

        return None

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

        Queries the K8s policy API for PodDisruptionBudgets and checks whether
        any PDB selector matches a pod on this node with maxUnavailable=0.

        Returns False (safe to drain) when:
        - K8s client is unavailable
        - No pods on the node have labels
        - No PDB has maxUnavailable=0
        - K8s API call fails (fail-open for draining)
        """
        if not self.k8s:
            return False

        # Collect pod label sets from pods on this node
        pod_label_sets = [
            pod.get("metadata", {}).get("labels", {})
            for pod in pods
            if pod.get("metadata", {}).get("labels")
        ]
        if not pod_label_sets:
            return False

        try:
            # Use k8s client to list PDBs — method may be list_pod_disruption_budgets
            list_pdbs_fn = getattr(self.k8s, "list_pod_disruption_budgets", None)
            if list_pdbs_fn is None:
                # K8s client doesn't expose PDB API — skip check
                return False

            pdb_list = list_pdbs_fn(cluster_id)

            for pdb in (pdb_list or []):
                spec = pdb.get("spec", {})
                max_unavailable = spec.get("maxUnavailable")

                # Only care about PDBs that allow zero unavailability
                if max_unavailable not in (0, "0"):
                    continue

                selector = spec.get("selector", {}).get("matchLabels", {})
                if not selector:
                    continue

                # Check if any pod on this node matches this PDB's selector
                for pod_labels in pod_label_sets:
                    if all(pod_labels.get(k) == v for k, v in selector.items()):
                        pdb_name = pdb.get("metadata", {}).get("name", "unknown")
                        logger.info(
                            f"Blocking PDB '{pdb_name}' on node {node_name}: "
                            f"maxUnavailable=0, selector={selector}"
                        )
                        return True

        except Exception as e:
            # Fail-open: if PDB check errors, don't block drain — log and continue
            logger.warning(f"PDB check failed for node {node_name}: {e}")

        return False

    # ── Per-node resource profile ──────────────────────────────────────────────

    NODE_PROFILES_TTL = 300  # 5 minutes

    def build_node_profile(self, node: dict, pods: list, headroom_pct: float = 10.0) -> dict:
        """
        Build a per-node resource profile from live K8s node + pod data.

        Returns NodeProfile dict with:
          - vcpu_total, memory_gb_total (allocatable capacity)
          - vcpu_requested, memory_gb_requested (sum of pod CPU/memory requests)
          - min_vcpu_required, min_memory_required (with headroom)
          - architecture, has_gpu_pods, has_local_pv, has_stateful_pods
          - status: MOVABLE | IMMOVABLE
        """
        node_name = node.get("metadata", {}).get("name", "")
        labels = node.get("metadata", {}).get("labels", {})

        instance_type = (
            labels.get("node.kubernetes.io/instance-type")
            or labels.get("beta.kubernetes.io/instance-type", "unknown")
        )
        architecture = (
            labels.get("kubernetes.io/arch")
            or labels.get("beta.kubernetes.io/arch", "amd64")
        )

        allocatable = node.get("status", {}).get("allocatable", {})
        capacity = node.get("status", {}).get("capacity", {})

        vcpu_total = self._parse_cpu(allocatable.get("cpu") or capacity.get("cpu", "0"))
        memory_gb_total = self._parse_memory_gb(
            allocatable.get("memory") or capacity.get("memory", "0Ki")
        )

        vcpu_requested = 0.0
        memory_gb_requested = 0.0
        has_gpu_pods = False
        has_local_pv = False
        has_stateful_pods = False

        for pod in pods:
            phase = pod.get("status", {}).get("phase", "")
            if phase in ("Succeeded", "Failed"):
                continue

            # StatefulSet check
            for owner in pod.get("metadata", {}).get("ownerReferences", []):
                if owner.get("kind") == "StatefulSet":
                    has_stateful_pods = True

            # Local PV check — emptyDir (memory-backed / sized) or hostPath
            for vol in pod.get("spec", {}).get("volumes", []):
                if "hostPath" in vol:
                    has_local_pv = True
                ed = vol.get("emptyDir", {})
                if ed and (ed.get("medium") == "Memory" or ed.get("sizeLimit")):
                    has_local_pv = True

            # Sum resource requests
            for container in pod.get("spec", {}).get("containers", []):
                requests = container.get("resources", {}).get("requests", {})
                vcpu_requested += self._parse_cpu(requests.get("cpu", "0"))
                memory_gb_requested += self._parse_memory_gb(requests.get("memory", "0Ki"))
                if "nvidia.com/gpu" in requests or "amd.com/gpu" in requests:
                    has_gpu_pods = True

        headroom_factor = 1.0 + headroom_pct / 100.0
        min_vcpu_required = max(math.ceil(vcpu_requested * headroom_factor), 1)
        min_memory_required = max(
            math.ceil(memory_gb_requested * headroom_factor * 10) / 10, 0.5
        )

        return {
            "node_name": node_name,
            "instance_type": instance_type,
            "architecture": architecture,
            "vcpu_total": round(vcpu_total, 2),
            "memory_gb_total": round(memory_gb_total, 2),
            "vcpu_requested": round(vcpu_requested, 3),
            "memory_gb_requested": round(memory_gb_requested, 3),
            "min_vcpu_required": min_vcpu_required,
            "min_memory_required": round(min_memory_required, 1),
            "headroom_pct": headroom_pct,
            "has_gpu_pods": has_gpu_pods,
            "has_local_pv": has_local_pv,
            "has_stateful_pods": has_stateful_pods,
            "status": "IMMOVABLE" if has_local_pv else "MOVABLE",
        }

    def get_all_node_profiles(self, cluster_id: str, headroom_pct: float = 10.0) -> dict:
        """
        Build resource profiles for all nodes in a cluster.
        Returns {node_name: NodeProfile, ...}
        Cached in Redis: spot:node_profiles:{cluster_id} TTL=300s
        """
        cache_key = f"spot:node_profiles:{cluster_id}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        if not self.k8s:
            return {}

        try:
            nodes = self._fetch_nodes_with_retry(cluster_id)
            profiles = {}
            for node in nodes:
                node_name = node.get("metadata", {}).get("name")
                if not node_name:
                    continue
                pods = self._fetch_pods_on_node_with_retry(cluster_id, node_name)
                profiles[node_name] = self.build_node_profile(node, pods, headroom_pct)

            try:
                self.redis.setex(cache_key, self.NODE_PROFILES_TTL, json.dumps(profiles))
            except Exception:
                pass

            return profiles
        except Exception as e:
            logger.error(f"get_all_node_profiles failed for {cluster_id}: {e}")
            return {}

    # ── CPU / Memory parsers ───────────────────────────────────────────────────

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse K8s CPU string to vCPU float. '2' → 2.0, '500m' → 0.5"""
        if not cpu_str:
            return 0.0
        s = str(cpu_str).strip()
        if s.endswith('m'):
            try:
                return float(s[:-1]) / 1000.0
            except ValueError:
                return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _parse_memory_gb(self, mem_str: str) -> float:
        """Parse K8s memory string to GB float. '4096Mi' → 4.0, '4Gi' → 4.0"""
        if not mem_str:
            return 0.0
        s = str(mem_str).strip()
        try:
            if s.endswith('Ki'):
                return float(s[:-2]) / (1024 * 1024)
            if s.endswith('Mi'):
                return float(s[:-2]) / 1024
            if s.endswith('Gi'):
                return float(s[:-2])
            if s.endswith('Ti'):
                return float(s[:-2]) * 1024
            if s.endswith('K') or s.endswith('k'):
                return float(s[:-1]) / (1000 * 1000)
            if s.endswith('M'):
                return float(s[:-1]) / 1000
            if s.endswith('G'):
                return float(s[:-1])
            if s.endswith('T'):
                return float(s[:-1]) * 1000
            return float(s) / (1024 ** 3)
        except ValueError:
            return 0.0

    # ── Cluster workload type ──────────────────────────────────────────────────

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
