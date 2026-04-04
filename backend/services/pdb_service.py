"""
PDB (PodDisruptionBudget) Service
==================================
Computes the maximum safe percentage of nodes that can be disrupted
simultaneously based on the strictest PodDisruptionBudget in a cluster.

Used by:
  - GET /clusters/{cluster_id}/optimization-settings  → returns pdb_safe_percent
  - auto_rebalancer.py  → caps batch size when respect_pdb_enabled is True

Cached in Redis for 5 minutes to avoid repeated K8s API calls.
"""

import json
import logging
from typing import Optional

import kubernetes.client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "pdb:safe_percent"
CACHE_TTL_SECONDS = 300  # 5 minutes


def get_pdb_safe_percent(cluster_id: str, k8s_client: kubernetes.client.ApiClient,
                         total_nodes: int) -> Optional[int]:
    """
    Returns the maximum percentage of nodes that can be disrupted
    based on the strictest PodDisruptionBudget in the cluster.

    Returns None if no PDBs exist (meaning no restriction).
    """
    try:
        policy_api = kubernetes.client.PolicyV1Api(k8s_client)
        pdb_list = policy_api.list_pod_disruption_budget_for_all_namespaces()
        if not pdb_list.items:
            return None

        max_unavailable_pct = 100  # start with 100% allowed

        for pdb in pdb_list.items:
            spec = pdb.spec
            if spec is None:
                continue

            if spec.max_unavailable is not None:
                mu = spec.max_unavailable
                mu_str = str(mu)
                if mu_str.endswith('%'):
                    pct = int(mu_str.rstrip('%'))
                else:
                    # Absolute number — convert to % of total nodes
                    abs_val = int(mu_str)
                    pct = (abs_val / total_nodes * 100) if total_nodes > 0 else 0
                max_unavailable_pct = min(max_unavailable_pct, pct)

            elif spec.min_available is not None:
                ma = spec.min_available
                ma_str = str(ma)
                if ma_str.endswith('%'):
                    min_avail_pct = int(ma_str.rstrip('%'))
                    pct = 100 - min_avail_pct
                else:
                    # Absolute number — maxUnavailable = total - minAvailable
                    abs_val = int(ma_str)
                    unavail = total_nodes - abs_val
                    pct = (unavail / total_nodes * 100) if total_nodes > 0 else 0
                max_unavailable_pct = min(max_unavailable_pct, max(0, pct))

        result = max(1, int(max_unavailable_pct))  # At least 1%
        return min(result, 100)

    except ApiException as e:
        logger.warning("[pdb_service] K8s API error fetching PDBs for cluster %s: %s", cluster_id, e.reason)
        return None
    except Exception as e:
        logger.exception("[pdb_service] Failed to compute PDB safe percent for cluster %s", cluster_id)
        return None


def get_pdb_safe_percent_cached(cluster_id: str, k8s_client: kubernetes.client.ApiClient,
                                total_nodes: int) -> Optional[int]:
    """
    Cached wrapper around get_pdb_safe_percent. Stores result in Redis for 5 minutes.
    Falls back to live computation if Redis is unavailable.
    """
    try:
        from backend.core.redis_client import get_redis_client
        redis = get_redis_client()
        cache_key = f"{REDIS_KEY_PREFIX}:{cluster_id}"

        cached = redis.get(cache_key)
        if cached is not None:
            val = cached.decode('utf-8') if isinstance(cached, bytes) else cached
            if val == 'null':
                return None
            return int(val)
    except Exception:
        redis = None

    # Cache miss or Redis unavailable — compute live
    result = get_pdb_safe_percent(cluster_id, k8s_client, total_nodes)

    if redis is not None:
        try:
            redis.setex(cache_key, CACHE_TTL_SECONDS, str(result) if result is not None else 'null')
        except Exception:
            pass

    return result


def get_pdb_safe_percent_for_cluster(cluster, db) -> Optional[int]:
    """
    High-level helper: given a Cluster ORM object, computes the PDB-safe
    percentage by creating a K8s client and counting total nodes.

    Used by API endpoints and auto_rebalancer.
    """
    try:
        from backend.services.karpenter_service import KarpenterService
        from backend.models.instance import Instance

        # Count total nodes in the cluster
        total_nodes = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running'
        ).count()

        if total_nodes == 0:
            return None

        # Create K8s client via KarpenterService (reuses EKS token logic)
        karp_svc = KarpenterService(db)
        k8s_client = karp_svc._get_k8s_client(cluster)

        return get_pdb_safe_percent_cached(cluster.id, k8s_client, total_nodes)

    except Exception as e:
        logger.warning("[pdb_service] Could not compute PDB safe percent for %s: %s", cluster.name, e)
        return None
