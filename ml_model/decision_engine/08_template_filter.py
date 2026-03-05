"""
Step 11: Template + Karpenter Filters
========================================
Source: backend/core/decision_engine.py (lines 487–503)
Related: backend/api/template_routes.py, backend/services/template_service.py

PURPOSE
-------
Apply user-defined instance template constraints and Karpenter configuration
to further narrow the candidate pool list.

TWO FILTER TYPES
-----------------

  1. Node Template Filter (user-configured)
     ----------------------------------------
     Users create "Node Templates" in the UI to define which instance families
     and spot pools are acceptable for their workloads.

     Template structure (stored in Redis):
       spot:template:{template_id} → JSON:
         {
           "instance_families": ["m5", "m6i", "c5"],  # Whitelist (empty = allow all)
           "blacklisted_pools": ["r5.xlarge:us-east-1a", ...],  # Blocked pools
           "max_vcpu": 16,    # CPU upper bound
           "max_memory_gb": 64  # Memory upper bound
         }

     Filter logic:
       - Blacklisted pools: BLOCK (regardless of family whitelist)
       - Family not in whitelist: BLOCK (if whitelist is non-empty)
       - vCPU > max_vcpu: BLOCK
       - Memory > max_memory_gb: BLOCK

  2. Karpenter Constraint Filter (Karpenter CRD requirements)
     ----------------------------------------------------------
     When Karpenter is managing the cluster's NodePool, its requirements
     (set in the NodePool CRD) constrain which instances are valid.

     Common Karpenter filters:
       architecture: "amd64" | "arm64" — CPU architecture requirement
       capacity_type: "spot" | "on-demand" — capacity type requirement

     Filter logic:
       - Pool architecture ≠ required architecture: BLOCK
       - Pool capacity type ≠ required type: BLOCK

WHEN FILTERS ARE APPLIED
-------------------------
Templates are optional — if no template_id is provided, this step is skipped.
Karpenter filters are optional — if no karpenter_filters dict, this step is skipped.

If BOTH filters remove all candidates → pipeline returns
  "No candidates pass template/Karpenter filters"
"""

import json
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Node Template Filter
# ---------------------------------------------------------------------------

def load_template(redis_client, template_id: str) -> Optional[Dict]:
    """
    Load a node template from Redis cache.

    Templates are stored by the backend's template_service.py and cached
    in Redis for fast lookup during the decision pipeline.

    Redis Key: spot:template:{template_id}
    Value:     JSON with instance_families, blacklisted_pools, etc.

    Args:
        redis_client: Redis connection
        template_id:  Template UUID

    Returns:
        Template dict, or None if not found (filter is then skipped)
    """
    cache_key = f"spot:template:{template_id}"
    data = redis_client.get(cache_key)
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except Exception:
        return None


def apply_template_filter(
    candidate_pools: List[Dict],
    template: Dict
) -> List[Dict]:
    """
    Filter candidate pools against a node template's constraints.

    Applies whitelist, blacklist, and resource limit checks.

    Args:
        candidate_pools: List of pool dicts with instance_type and az
        template:        Template dict from load_template()

    Returns:
        Filtered list — only pools that satisfy all template constraints

    Example:
        Template: families=["m5", "m6i"], blacklist=["m5.large:us-east-1a"]
        Input:  [m5.large:us-east-1a, m6i.large:us-east-1b, r5.large:us-east-1c]
        Output: [m6i.large:us-east-1b]
        Reason: m5.large:us-east-1a is blacklisted, r5 not in whitelist
    """
    whitelist = template.get("instance_families", [])  # Empty = allow all families
    blacklist = set(template.get("blacklisted_pools", []))  # "type:az" strings
    max_vcpu = template.get("max_vcpu", 0)          # 0 = no limit
    max_memory_gb = template.get("max_memory_gb", 0)  # 0 = no limit

    filtered = []
    for pool in candidate_pools:
        instance_type = pool.get("instance_type", "")
        az = pool.get("az", "")
        pool_key = f"{instance_type}:{az}"
        family = instance_type.split(".")[0] if "." in instance_type else instance_type

        # Check blacklist (always applied, regardless of whitelist)
        if pool_key in blacklist:
            continue

        # Check family whitelist (skip if whitelist is empty = allow all)
        if whitelist and family not in whitelist:
            continue

        # Check vCPU limit
        if max_vcpu > 0 and pool.get("vcpu", 0) > max_vcpu:
            continue

        # Check memory limit
        if max_memory_gb > 0 and pool.get("memory_gb", 0) > max_memory_gb:
            continue

        filtered.append(pool)

    return filtered


# ---------------------------------------------------------------------------
# Karpenter Constraint Filter
# ---------------------------------------------------------------------------

def apply_karpenter_filter(
    candidate_pools: List[Dict],
    karpenter_filters: Dict
) -> List[Dict]:
    """
    Filter candidates to match Karpenter NodePool requirements.

    Karpenter's NodePool CRD specifies which instance types and capacity
    types are allowed. The platform syncs these requirements and passes
    them as the karpenter_filters dict.

    Args:
        candidate_pools:   List of pool dicts
        karpenter_filters: Dict with optional keys:
                             architecture: "amd64" | "arm64"
                             capacity_type: "spot" | "on-demand"
                             instance_families: List[str] (additional whitelist)

    Returns:
        Filtered list — only pools matching all Karpenter constraints

    Example:
        Filters: {"architecture": "amd64", "capacity_type": "spot"}
        Input:  [m5.large(amd64,spot), m6g.large(arm64,spot), m5.large(amd64,on-demand)]
        Output: [m5.large(amd64,spot)]
    """
    filtered = []

    for pool in candidate_pools:
        # Architecture constraint (amd64 vs arm64)
        required_arch = karpenter_filters.get("architecture")
        if required_arch and pool.get("architecture") != required_arch:
            continue

        # Capacity type constraint (spot vs on-demand)
        required_capacity = karpenter_filters.get("capacity_type")
        if required_capacity and pool.get("capacity_type") != required_capacity:
            continue

        # Instance family constraint (additional whitelist from Karpenter NodePool)
        allowed_families = karpenter_filters.get("instance_families", [])
        if allowed_families:
            family = pool.get("instance_type", "").split(".")[0]
            if family not in allowed_families:
                continue

        filtered.append(pool)

    return filtered
