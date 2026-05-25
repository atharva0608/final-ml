"""
Workload Inspector
=================

Auto-detects stateful vs stateless workloads per cluster.
Scans Kubernetes API every 10 min, classifies each node.
Cache in Redis: spot:node_classification:{cluster_id}

Enhancement 1: build_workload_profile() provides per-controller enriched
signals (replicas, PDB, readiness, grace period, hostNetwork, mesh).
"""

from redis import Redis
from typing import Dict, List, Optional
from enum import Enum
import json
import logging
import math
import random

logger = logging.getLogger(__name__)

# W1.6a — Operator CRD owner kinds that indicate a database-managed pod.
# Imported lazily here so workload_inspector does not hard-depend on classifier
# at module load time (avoids circular import risk).
from backend.services.workload_classifier import OPERATOR_DB_OWNER_KINDS  # noqa: E402


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

    # EFS CSI provisioner names treated as spot-safe (ReadWriteMany / shared storage)
    _EFS_PROVISIONERS = frozenset({
        "efs.csi.aws.com",
        "efs.csi.eks.amazonaws.com",
    })
    # EBS and block storage provisioners treated as spot-unsafe
    _EBS_PROVISIONERS = frozenset({
        "ebs.csi.aws.com",
        "kubernetes.io/aws-ebs",
        "ebs.csi.eks.amazonaws.com",
    })

    def __init__(self, redis: Redis, k8s_client=None):
        self.redis = redis
        self.k8s = k8s_client
        # Per-scan StorageClass provisioner cache: sc_name → provisioner string
        self._sc_provisioner_cache: Dict[str, str] = {}

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

            # Build PVC → StorageClass provisioner map once per scan (Task 1.1)
            pvc_sc_map = self._build_pvc_sc_map(cluster_id)

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

                # 4. Check for PVC volumes (EFS is spot-safe, EBS is not)
                has_pvc = self._has_pvc_volumes(pods, pvc_sc_map)

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

            # ── LABEL NODES with workload type ────────────────────────────────
            # Queue LABEL_NODE agent actions so each node gets a Kubernetes label
            # (workload=stateless or workload=stateful) for Karpenter NodePool
            # affinity and operational visibility.
            self._queue_workload_labels(cluster_id, classification)

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
        from kubernetes import client as _k8s_c
        for attempt in range(max_retries):
            try:
                v1 = _k8s_c.CoreV1Api(self.k8s)
                return [n.to_dict() for n in v1.list_node().items]
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
        from kubernetes import client as _k8s_c
        for attempt in range(max_retries):
            try:
                v1 = _k8s_c.CoreV1Api(self.k8s)
                pods = v1.list_pod_for_all_namespaces(
                    field_selector=f"spec.nodeName={node_name}"
                )
                return [p.to_dict() for p in pods.items]
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

    def _build_pvc_sc_map(self, cluster_id: str) -> Dict[str, bool]:
        """
        Build a map of {(namespace, claimName): is_efs_safe} for all PVCs in the cluster.

        EFS-backed PVCs use ReadWriteMany and survive node loss — they are spot-safe.
        EBS-backed PVCs are block storage and are node-local — they are spot-unsafe.
        Unknown storage classes default to spot-unsafe (safe fallback).

        Returns empty dict when k8s client is unavailable or methods not exposed.
        """
        if not self.k8s:
            return {}

        result: Dict[str, bool] = {}
        try:
            # 1. Fetch all StorageClasses and build provisioner lookup
            list_sc_fn = getattr(self.k8s, "list_storage_classes", None)
            if list_sc_fn:
                sc_list = list_sc_fn(cluster_id) or []
                for sc in sc_list:
                    sc_name = sc.get("metadata", {}).get("name", "")
                    provisioner = sc.get("provisioner", "")
                    if sc_name:
                        self._sc_provisioner_cache[sc_name] = provisioner

            # 2. Fetch all PVCs and map (namespace, claimName) → is_efs_safe
            list_pvc_fn = getattr(self.k8s, "list_pvcs_all_namespaces", None)
            if list_pvc_fn is None:
                list_pvc_fn = getattr(self.k8s, "list_persistent_volume_claims", None)
            if list_pvc_fn:
                pvc_list = list_pvc_fn(cluster_id) or []
                for pvc in pvc_list:
                    ns = pvc.get("metadata", {}).get("namespace", "")
                    name = pvc.get("metadata", {}).get("name", "")
                    sc_name = pvc.get("spec", {}).get("storageClassName", "")
                    access_modes = pvc.get("spec", {}).get("accessModes", [])

                    # ReadWriteMany implies shared storage (EFS-like) — spot-safe
                    if "ReadWriteMany" in access_modes:
                        result[(ns, name)] = True
                        continue

                    provisioner = self._sc_provisioner_cache.get(sc_name, "")
                    if provisioner in self._EFS_PROVISIONERS:
                        result[(ns, name)] = True  # EFS → spot-safe
                    else:
                        result[(ns, name)] = False  # EBS or unknown → spot-unsafe

        except Exception as e:
            logger.warning(f"[WorkloadInspector] PVC/SC map build failed for {cluster_id}: {e}")

        return result

    def _has_pvc_volumes(self, pods: list, pvc_sc_map: Optional[Dict[str, bool]] = None) -> bool:
        """
        Check if any pod has PVC volumes that require stateful (block storage) placement.

        EFS-backed PVCs (ReadWriteMany) are spot-safe and do NOT mark the node stateful.
        EBS-backed PVCs are block-local and DO mark the node stateful.
        When pvc_sc_map is absent or a PVC cannot be resolved, defaults to stateful (safe).
        """
        for pod in pods:
            ns = pod.get("metadata", {}).get("namespace", "")
            volumes = pod.get("spec", {}).get("volumes", [])
            for vol in volumes:
                pvc_ref = vol.get("persistentVolumeClaim")
                if pvc_ref:
                    claim_name = pvc_ref.get("claimName", "")
                    if pvc_sc_map is not None:
                        is_efs_safe = pvc_sc_map.get((ns, claim_name))
                        if is_efs_safe is True:
                            continue  # EFS PVC — skip, spot-safe
                        # False or None (unknown) → stateful
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

                # Task 1.2 — Stale PDB check: if the PDB currently protects zero pods
                # (currentHealthy == 0, desiredHealthy == 0) its selector matches no
                # running pods — it is stale and should NOT block drain.
                pdb_status = pdb.get("status", {})
                current_healthy = pdb_status.get("currentHealthy", -1)
                desired_healthy = pdb_status.get("desiredHealthy", -1)
                if current_healthy == 0 and desired_healthy == 0:
                    pdb_name = pdb.get("metadata", {}).get("name", "unknown")
                    logger.debug(
                        f"[WorkloadInspector] Skipping stale PDB '{pdb_name}' on node {node_name}: "
                        f"currentHealthy=0, desiredHealthy=0 (selector matches no pods)"
                    )
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

    # ── Workload node labeling ─────────────────────────────────────────────────

    def _queue_workload_labels(self, cluster_id: str, classification: Dict):
        """Queue LABEL_NODE agent actions to apply workload=stateless|stateful labels.

        Uses a Redis dedup key to avoid re-labeling nodes that haven't changed
        classification since the last scan.
        """
        try:
            from backend.core.database import SessionLocal
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
            from datetime import datetime, timedelta
            import uuid

            dedup_key = f"spot:workload_labels:{cluster_id}"
            prev_raw = self.redis.get(dedup_key)
            prev_labels = {}
            if prev_raw:
                import json as _json_wl
                prev_labels = _json_wl.loads(prev_raw)

            actions_to_create = []
            for node_name, status in classification.items():
                label_value = "stateless" if status == NodeStatus.STATELESS_ELIGIBLE else "stateful"
                # Skip if label hasn't changed
                if prev_labels.get(node_name) == label_value:
                    continue
                actions_to_create.append((node_name, label_value))

            if not actions_to_create:
                return

            db = SessionLocal()
            try:
                for node_name, label_value in actions_to_create:
                    action = AgentAction(
                        id=str(uuid.uuid4()),
                        cluster_id=cluster_id,
                        action_type=AgentActionType.LABEL_NODE,
                        payload={
                            "node_name": node_name,
                            "labels": {"workload": label_value},
                        },
                        status=AgentActionStatus.PENDING,
                        priority=0,
                        created_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(minutes=30),
                    )
                    db.add(action)
                db.commit()
                logger.info(
                    f"[WorkloadInspector] Queued {len(actions_to_create)} LABEL_NODE actions "
                    f"for cluster {cluster_id}"
                )
            finally:
                db.close()

            # Update dedup cache with current labels
            import json as _json_wl2
            current_labels = {
                n: ("stateless" if s == NodeStatus.STATELESS_ELIGIBLE else "stateful")
                for n, s in classification.items()
            }
            self.redis.setex(dedup_key, self.CLASSIFICATION_TTL, _json_wl2.dumps(current_labels))

        except Exception as e:
            logger.warning(f"[WorkloadInspector] Failed to queue workload labels: {e}")

    # ── Cluster workload type ──────────────────────────────────────────────────

    # ── Enhancement 1: Per-controller workload profile ─────────────────────────

    WORKLOAD_PROFILE_TTL = 540  # same as classification

    def build_workload_profile(
        self, cluster_id: str, node_name: str, pods: list,
        scaled_objects: Optional[list] = None,
        hpas: Optional[list] = None,
    ) -> Dict[str, dict]:
        """
        Build per-controller workload profiles for pods on a single node.

        Groups pods by owning controller (Deployment, StatefulSet, DaemonSet),
        computes PDB health, readiness probe presence, grace period, host_network,
        service-mesh sidecar detection, and fragility level.

        Returns {"{namespace}/{controller_name}": profile_dict, ...}
        Each profile is also cached individually under
        ``spot:workload_profile:{cluster_id}:{namespace}/{controller_name}``.
        """
        profiles: Dict[str, dict] = {}

        # ── Group pods by controller ──────────────────────────────────────────
        controller_pods: Dict[str, List[dict]] = {}
        for pod in pods:
            meta = pod.get("metadata", {})
            namespace = meta.get("namespace", "default")
            owners = meta.get("ownerReferences", [])
            if not owners:
                continue

            owner = owners[0]
            kind = owner.get("kind", "")
            name = owner.get("name", "")

            # ReplicaSets are owned by Deployments — resolve one level up
            if kind == "ReplicaSet":
                # Naming convention: <deployment>-<hash>
                parts = name.rsplit("-", 1)
                if len(parts) == 2 and len(parts[1]) >= 6:
                    name = parts[0]
                    kind = "Deployment"

            # W1.6a — Database operator CRD owners (e.g. CloudNativePG "Cluster",
            # CrunchyData "PostgresCluster", Percona, Zalando, Strimzi, etc.).
            # Mark them as "OperatorStateful" so the classifier can reliably assign TIER_1.
            if kind in OPERATOR_DB_OWNER_KINDS:
                kind = "OperatorStateful"

            key = f"{namespace}/{name}"
            controller_pods.setdefault(key, []).append(
                {"pod": pod, "kind": kind, "name": name, "namespace": namespace}
            )

        # ── Fetch PDBs once for the whole node ────────────────────────────────
        all_pdbs = self._fetch_pdbs(cluster_id)

        # ── Build profile per controller ──────────────────────────────────────
        for ctrl_key, entries in controller_pods.items():
            kind = entries[0]["kind"]
            name = entries[0]["name"]
            namespace = entries[0]["namespace"]
            ctrl_pods = [e["pod"] for e in entries]

            replica_count = len(ctrl_pods)

            # PDB analysis
            pdb_info = self._analyse_pdb(ctrl_pods, all_pdbs)

            # Readiness probe
            readiness_defined = False
            min_initial_delay = None
            for p in ctrl_pods:
                for c in p.get("spec", {}).get("containers", []):
                    rp = c.get("readinessProbe")
                    if rp:
                        readiness_defined = True
                        delay = rp.get("initialDelaySeconds", 0)
                        if min_initial_delay is None or delay < min_initial_delay:
                            min_initial_delay = delay

            # Grace period (max across pods in controller)
            grace = max(
                (p.get("spec", {}).get("terminationGracePeriodSeconds") or 30 for p in ctrl_pods),
                default=30,
            )

            # Host network
            host_network = any(
                p.get("spec", {}).get("hostNetwork") for p in ctrl_pods
            )

            # Service-mesh sidecar detection
            _MESH_CONTAINERS = {"istio-proxy", "linkerd-proxy", "envoy", "consul-connect-inject"}
            has_mesh = False
            for p in ctrl_pods:
                cnames = {c.get("name", "") for c in p.get("spec", {}).get("containers", [])}
                if cnames & _MESH_CONTAINERS:
                    has_mesh = True
                    break

            # Problem 1: preStop hook detection — kube-proxy propagation race
            has_prestop = False
            for p in ctrl_pods:
                for c in p.get("spec", {}).get("containers", []):
                    lifecycle = c.get("lifecycle", {})
                    if lifecycle.get("preStop"):
                        has_prestop = True
                        break
                if has_prestop:
                    break

            # Fragility level
            fragility = "NORMAL"
            if host_network:
                fragility = "HOST_NETWORK"
            elif replica_count <= 1 and not pdb_info["pdb_defined"] and not readiness_defined:
                fragility = "FRAGILE"
            elif replica_count <= 1:
                fragility = "LOW_REDUNDANCY"

            # W1.6 — PVC count from pod volumes (needed by classifier for TIER_1 detection).
            pvc_count = 0
            for p in ctrl_pods:
                for vol in p.get("spec", {}).get("volumes", []):
                    if vol.get("persistentVolumeClaim"):
                        pvc_count += 1

            # W1.6 — Pod labels and annotations (first pod is representative).
            first_pod_meta = ctrl_pods[0].get("metadata", {}) if ctrl_pods else {}
            pod_labels      = first_pod_meta.get("labels", {}) or {}
            pod_annotations = first_pod_meta.get("annotations", {}) or {}

            profile = {
                "controller_name": name,
                "controller_kind": kind,
                "namespace": namespace,
                "replica_count": replica_count,
                "pdb_defined": pdb_info["pdb_defined"],
                "pdb_healthy_count": pdb_info["pdb_healthy_count"],
                "pdb_min_available": pdb_info["pdb_min_available"],
                "pdb_satisfies_budget": pdb_info["pdb_satisfies_budget"],
                "readiness_probe_defined": readiness_defined,
                "readiness_initial_delay_seconds": min_initial_delay,
                "termination_grace_period_seconds": grace,
                "has_service_mesh_sidecar": has_mesh,
                "has_prestop_hook": has_prestop,
                "host_network": host_network,
                "fragility_level": fragility,
                # W1.6 — Fields needed by classifier
                "pvc_count":       pvc_count,
                "pod_labels":      pod_labels,
                "pod_annotations": pod_annotations,
                # W1.6 — KEDA fields (populated by K3 scan step; default to False/None
                # for backward compat when K3 has not run yet)
                "keda_managed":               False,
                "scaled_object_name":         None,
                "scaled_object_trigger_types": [],
                "keda_min_replicas":          None,
                "keda_max_replicas":          None,
                "keda_paused":                False,
                "hpa_keda_conflict":          False,
            }

            # K3.2 — Populate KEDA fields from the pre-fetched ScaledObjects.
            # Match by scaleTargetRef.name + namespace to avoid cross-ns collisions.
            if scaled_objects:
                for _so in scaled_objects:
                    _so_spec = _so.get("spec", {})
                    _so_meta = _so.get("metadata", {})
                    _target  = _so_spec.get("scaleTargetRef", {})
                    if (
                        _target.get("name") == name
                        and _so_meta.get("namespace") == namespace
                    ):
                        _triggers = _so_spec.get("triggers") or []
                        _annotations = _so_meta.get("annotations") or {}
                        profile["keda_managed"]              = True
                        profile["scaled_object_name"]        = _so_meta.get("name")
                        profile["scaled_object_trigger_types"] = [
                            t.get("type") for t in _triggers if t.get("type")
                        ]
                        profile["keda_min_replicas"]         = _so_spec.get("minReplicaCount")
                        profile["keda_max_replicas"]         = _so_spec.get("maxReplicaCount")
                        profile["keda_paused"]               = bool(
                            _so_spec.get("paused", False)
                            or _annotations.get("autoscaling.keda.sh/paused", "").lower() == "true"
                        )
                        break

            # K3.3 — HPA + KEDA conflict detection: both targeting the same controller.
            if profile["keda_managed"] and hpas:
                for _hpa in hpas:
                    _hpa_spec = _hpa.get("spec", {})
                    _hpa_target = _hpa_spec.get("scaleTargetRef", {})
                    _hpa_ns = _hpa.get("metadata", {}).get("namespace")
                    if _hpa_target.get("name") == name and _hpa_ns == namespace:
                        profile["hpa_keda_conflict"] = True
                        break

            profile.update({  # re-open profile dict to maintain structure below
                # W1.6 — CRD owner kind (set by owner resolution above for OperatorStateful)
                "crd_owner_kind": owners[0].get("kind") if owners else None if not ctrl_pods
                                  else (ctrl_pods[0].get("metadata", {}).get("ownerReferences") or [{}])[0].get("kind"),
            })

            # W1.7 — Classify the workload (uses profile + no agent data at this layer;
            # full image/port enrichment happens when pod_spec_fields are provided via
            # the batch metrics ingestion path).
            try:
                from backend.services.workload_classifier import classify_workload
                classification_result = classify_workload(profile)
                profile.update({
                    "workload_tier":              classification_result["tier"],
                    "tier_name":                  classification_result["tier_name"],
                    "detected_app_type":          classification_result["detected_app_type"],
                    "migration_policy":           classification_result["migration_policy"],
                    "classification_reasons":     classification_result["classification_reasons"],
                    "classification_confidence":  classification_result["classification_confidence"],
                })
            except Exception as _cls_err:
                logger.warning(f"[WorkloadInspector] classification failed for {ctrl_key}: {_cls_err}")
                profile.update({
                    "workload_tier":             4,
                    "tier_name":                 "SPOT_ELIGIBLE",
                    "detected_app_type":         "unknown",
                    "migration_policy":          "spot_eligible",
                    "classification_reasons":    ["classification_error"],
                    "classification_confidence": 0.0,
                })

            profiles[ctrl_key] = profile

            # Cache individually
            cache_key = f"spot:workload_profile:{cluster_id}:{ctrl_key}"
            try:
                self.redis.setex(cache_key, self.WORKLOAD_PROFILE_TTL, json.dumps(profile))
            except Exception:
                pass

            # W2.1 — Write separate tier key for fast rebalancer reads (no profile deserialise).
            # Uses the same TTL as the profile for consistency.
            tier_cache_key = f"spot:workload_tier:{cluster_id}:{ctrl_key}"
            try:
                tier_payload = json.dumps({
                    "tier":        profile.get("workload_tier", 4),
                    "tier_name":   profile.get("tier_name", "SPOT_ELIGIBLE"),
                    "policy":      profile.get("migration_policy", "spot_eligible"),
                    "confidence":  profile.get("classification_confidence", 0.0),
                    "app_type":    profile.get("detected_app_type", "unknown"),
                })
                self.redis.setex(tier_cache_key, self.WORKLOAD_PROFILE_TTL, tier_payload)
            except Exception:
                pass

        return profiles

    def get_workload_profile(
        self, cluster_id: str, namespace: str, controller_name: str,
    ) -> Optional[dict]:
        """Read a cached workload profile for a single controller."""
        cache_key = f"spot:workload_profile:{cluster_id}:{namespace}/{controller_name}"
        try:
            raw = self.redis.get(cache_key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def get_workload_tier(
        self, cluster_id: str, namespace: str, controller_name: str,
    ) -> Optional[dict]:
        """W2.2 — Read the lightweight tier summary (no full profile deserialise needed)."""
        cache_key = f"spot:workload_tier:{cluster_id}:{namespace}/{controller_name}"
        try:
            raw = self.redis.get(cache_key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    # ── Enhancement 1-B: Misconfig recommendations ─────────────────────────────

    def collect_misconfig_recommendations(self, profile: dict) -> List[dict]:
        """
        Emit structured misconfig recommendations from a workload profile.

        Returns list of dicts: [{severity, code, message, controller, namespace}]
        """
        recs: List[dict] = []
        ctrl = profile.get("controller_name", "?")
        ns = profile.get("namespace", "?")

        if not profile.get("readiness_probe_defined"):
            recs.append({
                "severity": "HIGH",
                "code": "MISSING_READINESS_PROBE",
                "message": (
                    "Add readiness probe: no trust boundary for ready state. "
                    "Karpenter and the rebalancer cannot verify pod health after migration."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        if not profile.get("pdb_defined"):
            recs.append({
                "severity": "HIGH",
                "code": "MISSING_PDB",
                "message": (
                    "Add PodDisruptionBudget: no protection during involuntary disruptions. "
                    "Pods may all be evicted simultaneously."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        grace = profile.get("termination_grace_period_seconds") or 30
        if grace < 30:
            recs.append({
                "severity": "MEDIUM",
                "code": "LOW_GRACE_PERIOD",
                "message": (
                    f"Increase terminationGracePeriodSeconds (currently {grace}s): "
                    "below safe drain threshold of 30s."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        if (
            profile.get("pdb_defined")
            and profile.get("pdb_min_available") is not None
            and profile.get("replica_count")
            and profile["pdb_min_available"] >= profile["replica_count"]
        ):
            recs.append({
                "severity": "HIGH",
                "code": "STALE_PDB",
                "message": (
                    f"PDB misconfigured: minAvailable ({profile['pdb_min_available']}) "
                    f"equals total replicas ({profile['replica_count']}) — "
                    "will always block eviction."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        # Problem 1: Detect missing preStop hook — kube-proxy propagation race
        if not profile.get("has_prestop_hook"):
            recs.append({
                "severity": "HIGH",
                "code": "MISSING_PRESTOP_HOOK",
                "message": (
                    "Add lifecycle.preStop hook (e.g. sleep 5): without it, kube-proxy "
                    "may still route traffic to this pod after SIGTERM is sent. "
                    "In clusters with 50+ nodes, use sleep 10-15."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        # Problem 4: Single-replica workload with no PDB — most common real failure
        if (
            profile.get("replica_count", 0) == 1
            and not profile.get("pdb_defined")
        ):
            recs.append({
                "severity": "CRITICAL",
                "code": "SINGLE_REPLICA_NO_PDB",
                "message": (
                    "Single-replica workload with no PDB: eviction causes complete "
                    "outage until replacement pod passes readiness probe (10-60s). "
                    "Add a PDB or increase replicas to ≥2."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        # K3.4 — HPA + KEDA ScaledObject conflict
        if profile.get("hpa_keda_conflict"):
            recs.append({
                "severity": "HIGH",
                "code": "MISCONFIG_HPA_KEDA_CONFLICT",
                "message": (
                    "Both an HPA and a KEDA ScaledObject are targeting this workload. "
                    "This causes conflicting scaling decisions and unpredictable behaviour. "
                    "Remove the HPA or the ScaledObject — not both."
                ),
                "controller": ctrl,
                "namespace": ns,
            })

        return recs

    def build_all_profiles_for_cluster(self, cluster_id: str) -> Dict[str, dict]:
        """
        Build workload profiles for ALL controllers in a cluster.
        Also collects and caches misconfig recommendations.

        Called from the control-plane scan loop.
        """
        all_profiles: Dict[str, dict] = {}
        all_recs: List[dict] = []

        if not self.k8s:
            return all_profiles

        try:
            # K3 — Pre-fetch KEDA ScaledObjects and HPAs once for the whole cluster
            # so each build_workload_profile() call can populate KEDA fields cheaply.
            _scaled_objects = self._fetch_scaled_objects(cluster_id)
            _hpas = self._fetch_hpas(cluster_id)

            nodes = self._fetch_nodes_with_retry(cluster_id)
            for node in nodes:
                node_name = node.get("metadata", {}).get("name")
                if not node_name:
                    continue
                pods = self._fetch_pods_on_node_with_retry(cluster_id, node_name)
                profiles = self.build_workload_profile(
                    cluster_id, node_name, pods,
                    scaled_objects=_scaled_objects,
                    hpas=_hpas,
                )
                for key, profile in profiles.items():
                    if key not in all_profiles:
                        all_profiles[key] = profile
                        all_recs.extend(self.collect_misconfig_recommendations(profile))

            # Cache cluster-wide recommendations
            recs_key = f"spot:workload_recommendations:{cluster_id}"
            self.redis.setex(recs_key, self.WORKLOAD_PROFILE_TTL, json.dumps(all_recs))

            logger.info(
                f"[WorkloadInspector] Built {len(all_profiles)} workload profiles "
                f"with {len(all_recs)} recommendations for cluster {cluster_id}"
            )
        except Exception as e:
            logger.error(f"[WorkloadInspector] build_all_profiles_for_cluster failed: {e}")

        return all_profiles

    # ── PDB helpers ────────────────────────────────────────────────────────────

    def _fetch_pdbs(self, cluster_id: str) -> list:
        """Fetch PodDisruptionBudgets via the K8s client."""
        if not self.k8s:
            return []
        fn = getattr(self.k8s, "list_pod_disruption_budgets", None)
        if fn is None:
            return []
        try:
            return fn(cluster_id) or []
        except Exception as e:
            logger.warning(f"[WorkloadInspector] Failed to fetch PDBs: {e}")
            return []

    def _fetch_scaled_objects(self, cluster_id: str) -> list:
        """K3 — Fetch all KEDA ScaledObjects via the K8s client wrapper.

        Returns raw dict representations of ScaledObjects (or [] if KEDA not present).
        """
        if not self.k8s:
            return []
        fn = getattr(self.k8s, "list_scaled_objects", None)
        if fn is None:
            return []
        try:
            return fn(cluster_id) or []
        except Exception as e:
            logger.debug(f"[WorkloadInspector] ScaledObject fetch skipped for {cluster_id}: {e}")
            return []

    def _fetch_hpas(self, cluster_id: str) -> list:
        """K3 — Fetch all HorizontalPodAutoscalers via the K8s client wrapper.

        Returns raw dict representations (or [] if method not exposed).
        """
        if not self.k8s:
            return []
        fn = getattr(self.k8s, "list_horizontal_pod_autoscalers", None)
        if fn is None:
            return []
        try:
            return fn(cluster_id) or []
        except Exception as e:
            logger.debug(f"[WorkloadInspector] HPA fetch skipped for {cluster_id}: {e}")
            return []

    def _analyse_pdb(self, pods: list, all_pdbs: list) -> dict:
        """
        Check whether any PDB covers the given pods.

        Returns {pdb_defined, pdb_healthy_count, pdb_min_available, pdb_satisfies_budget}.
        """
        result = {
            "pdb_defined": False,
            "pdb_healthy_count": 0,
            "pdb_min_available": None,
            "pdb_satisfies_budget": True,
        }

        pod_label_sets = [
            p.get("metadata", {}).get("labels", {})
            for p in pods
            if p.get("metadata", {}).get("labels")
        ]
        if not pod_label_sets or not all_pdbs:
            return result

        for pdb in all_pdbs:
            spec = pdb.get("spec", {})
            selector = spec.get("selector", {}).get("matchLabels", {})
            if not selector:
                continue

            # Check if PDB matches any of our pods
            matched = False
            for labels in pod_label_sets:
                if all(labels.get(k) == v for k, v in selector.items()):
                    matched = True
                    break
            if not matched:
                continue

            result["pdb_defined"] = True

            status = pdb.get("status", {})
            healthy = status.get("currentHealthy", 0)
            result["pdb_healthy_count"] = healthy

            min_avail = spec.get("minAvailable")
            if min_avail is not None:
                try:
                    result["pdb_min_available"] = int(min_avail)
                except (ValueError, TypeError):
                    pass  # percentage-based — skip for now

            if result["pdb_min_available"] is not None:
                result["pdb_satisfies_budget"] = healthy >= result["pdb_min_available"]

            break  # use first matching PDB

        return result

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
