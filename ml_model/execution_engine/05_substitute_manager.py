"""
Step 5 (Execution): Substitute Manager — Warm Spare Lifecycle
==============================================================
Source: backend/services/substitute_manager.py

PURPOSE
-------
The Substitute Manager ensures ZERO-DOWNTIME during spot node migrations.

The problem it solves:
  - Draining a node evicts pods → they reschedule on other nodes
  - If the cluster is at capacity, there's no room for evicted pods
  - Pods could be PENDING (homeless) for minutes while Karpenter provisions
  - This = downtime for the application

The solution:
  - BEFORE draining the source node, pre-provision a "warm spare" (substitute)
  - The spare is a spot node already running and READY in K8s
  - When source is drained, evicted pods land INSTANTLY on the spare
  - No downtime gap

WARM SPARE ARCHITECTURE
------------------------
The system maintains one warm spare per cluster at all times (24×7):
  - Spare is the cheapest spot pool that can handle the cluster's LARGEST node's workload
  - When the spare is "used" (becomes active after a drain), a NEW spare is immediately provisioned
  - Result: There's always a ready spare, even after migration

STATE MACHINE (Redis-backed)
------------------------------
All state is stored in Redis (not DB) for speed and simplicity.

  IDLE → PREWARMING → READY → ACTIVE → RELEASING → IDLE

  IDLE:       No substitute running. Cluster is on its own.
  PREWARMING: Karpenter is provisioning the substitute node.
              Short TTL (5 min timeout). If Karpenter fails: → IDLE.
  READY:      Substitute node is K8s-READY. Available for use.
              Warm spare has NO TTL — stays forever until used.
              Normal substitute has 1-hour timeout (not used → IDLE).
  ACTIVE:     Substitute is being used (drain in progress or just completed).
              6-hour TTL. After 6h: handback timer triggers → RELEASING → IDLE.
  RELEASING:  Short cleanup state (60s TTL) while we record termination.
  IDLE:       Cycle complete. New warm spare provisioning triggered.

REDIS KEYS
-----------
  spot:substitute:state:{cluster_id}    — Current state string (TTL varies by state)
  spot:substitute:meta:{cluster_id}     — JSON metadata (instance type, AZ, cost, etc.)
  spot:substitute:next_spare:{cluster_id} — Replacement spare being prewarmed while primary ACTIVE

METADATA STORED (per cluster)
-------------------------------
  {
    "is_warm_spare": true,
    "substitute_instance_type": "c5.large",
    "substitute_az": "ap-south-1b",
    "substitute_lifecycle": "spot",
    "spot_price_hourly": 0.0340,
    "monthly_cost": 24.48,
    "risk_score": 0.08,
    "target_vcpu": 2,
    "target_memory_gb": 8.0,
    "target_node_instance_type": "m5.large",
    "compatible_with": "Any node ≤ 2 vCPU / 8.0 GB",
    "started_at": "2026-03-04T10:00:00Z",
    "validated_at": "2026-03-04T10:00:01Z",
    "promoted_at": null,
    "handback_at": null
  }

SUBSTITYTE TYPE SELECTION
---------------------------
Based on cluster optimization mode:
  NO_DOWNTIME_FIRST → on-demand substitute (same instance type, different AZ)
  BALANCED / COST_FIRST → spot substitute (ML-ranked cheapest compatible pool)

DRYRUN VALIDATION
------------------
Before marking a substitute READY, EC2 DryRun is performed:
  boto3.ec2.run_instances(..., DryRun=True)
  → 200 = would have succeeded (DryRunOperation error code means PASS)
  → Error != DryRunOperation = would fail (capacity unavailable, permissions, etc.)

Up to 3 candidate pools are tried in order. If all fail DryRun → IDLE.
The DryRun failure rate is stored in Redis for Step 9's capacity failure probability.

COST DRIFT MONITORING
----------------------
While in ACTIVE state, the substitute's spot price is monitored.
If price drifts > 15% above the original price:
  → Alert logged
  → Recommendation: replace substitute with cheaper alternative

WARM SPARE SIZING
------------------
The warm spare is sized to handle the LARGEST node in the cluster:
  max_node = max(all instances, key=vcpu × memory_gb)
  → Find cheapest spot pool with vcpu ≥ max_node.vcpu AND memory ≥ max_node.memory_gb
  → Use this as the warm spare type

This ensures the spare can absorb ANY node drain in the cluster
(not just small nodes).
"""

from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# State Machine States
# ---------------------------------------------------------------------------

class SubstituteState(str, Enum):
    """
    Lifecycle states for the substitute instance.

    Each state has different Redis TTL behavior:
      IDLE:        No TTL (key may not exist)
      PREWARMING:  5-minute TTL (times out if Karpenter fails)
      READY:       No TTL for warm spare (stays forever), 1-hour for regular
      ACTIVE:      6-hour TTL (handback timer)
      RELEASING:   60-second TTL (cleanup window)
    """
    IDLE = "IDLE"
    PREWARMING = "PREWARMING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    RELEASING = "RELEASING"


# ---------------------------------------------------------------------------
# Configuration Constants
# ---------------------------------------------------------------------------

HANDBACK_HOURS = 6                # Auto-release substitute after 6 hours
MAX_COST_DRIFT_PERCENT = 15       # Alert if spot price drifts > 15%
PREWARMING_TIMEOUT_MINUTES = 5    # Give up on PREWARMING after 5 minutes
READY_TIMEOUT_HOURS = 1           # Non-warm-spare READY timeout
MAX_CANDIDATES = 3                # Try up to 3 substitute candidates


# ---------------------------------------------------------------------------
# Instance size lookup (used for substitute sizing)
# ---------------------------------------------------------------------------

# Maps instance_type → (vcpu, memory_gb)
# Used to find compatible substitute pools for each node size
INSTANCE_VCPU_MEM = {
    "t3.nano": (2, 0.5), "t3.micro": (2, 1), "t3.small": (2, 2), "t3.medium": (2, 4),
    "t3.large": (2, 8), "t3.xlarge": (4, 16), "t3.2xlarge": (8, 32),
    "t4g.micro": (2, 1), "t4g.small": (2, 2), "t4g.medium": (2, 4), "t4g.large": (2, 8),
    "m5.large": (2, 8), "m5.xlarge": (4, 16), "m5.2xlarge": (8, 32),
    "m6i.large": (2, 8), "m6i.xlarge": (4, 16), "m6i.2xlarge": (8, 32),
    "c5.large": (2, 4), "c5.xlarge": (4, 8), "c5.2xlarge": (8, 16),
    "c6i.large": (2, 4), "c6i.xlarge": (4, 8), "c6i.2xlarge": (8, 16),
    "r5.large": (2, 16), "r5.xlarge": (4, 32), "r5.2xlarge": (8, 64),
}


# ---------------------------------------------------------------------------
# State transition helpers
# ---------------------------------------------------------------------------

def get_substitute_state(redis_client, cluster_id: str) -> SubstituteState:
    """
    Read current substitute state from Redis.

    Args:
        redis_client: Redis connection
        cluster_id:   Cluster identifier

    Returns:
        Current SubstituteState (defaults to IDLE if key missing)
    """
    state_key = f"spot:substitute:state:{cluster_id}"
    state = redis_client.get(state_key)
    if not state:
        return SubstituteState.IDLE
    state_str = state.decode("utf-8") if isinstance(state, bytes) else state
    try:
        return SubstituteState(state_str)
    except ValueError:
        return SubstituteState.IDLE


def transition_to_prewarming(redis_client, cluster_id: str, metadata: dict):
    """
    Transition to PREWARMING state with 5-minute timeout.

    Call this when starting substitute provisioning via Karpenter.
    If Karpenter doesn't provision within 5 minutes, the state expires → IDLE.

    Args:
        redis_client: Redis connection
        cluster_id:   Cluster identifier
        metadata:     Initial metadata dict (target node info, etc.)
    """
    import json
    timeout = PREWARMING_TIMEOUT_MINUTES * 60

    redis_client.set(f"spot:substitute:state:{cluster_id}", SubstituteState.PREWARMING.value)
    redis_client.expire(f"spot:substitute:state:{cluster_id}", timeout)

    redis_client.set(f"spot:substitute:meta:{cluster_id}", json.dumps(metadata))
    redis_client.expire(f"spot:substitute:meta:{cluster_id}", timeout)


def transition_to_ready(redis_client, cluster_id: str, metadata: dict, is_warm_spare: bool = True):
    """
    Transition to READY state after substitute node passes DryRun validation.

    Warm spare: NO TTL — stays in READY until used.
    Regular substitute: 1-hour TTL — expires if not promoted.

    Args:
        redis_client:  Redis connection
        cluster_id:    Cluster identifier
        metadata:      Full metadata with instance_type, az, price, etc.
        is_warm_spare: If True, no TTL (permanent warm spare)
    """
    import json

    redis_client.set(f"spot:substitute:state:{cluster_id}", SubstituteState.READY.value)
    if not is_warm_spare:
        redis_client.expire(f"spot:substitute:state:{cluster_id}", READY_TIMEOUT_HOURS * 3600)

    redis_client.set(f"spot:substitute:meta:{cluster_id}", json.dumps(metadata))
    if not is_warm_spare:
        redis_client.expire(f"spot:substitute:meta:{cluster_id}", READY_TIMEOUT_HOURS * 3600)


def transition_to_active(redis_client, cluster_id: str):
    """
    Promote substitute from READY to ACTIVE (start using it for migration).

    Sets 6-hour handback timer — after which the substitute is released.

    Args:
        redis_client: Redis connection
        cluster_id:   Cluster identifier
    """
    import json
    from datetime import datetime, timedelta

    handback_seconds = HANDBACK_HOURS * 3600
    handback_at = datetime.utcnow() + timedelta(hours=HANDBACK_HOURS)

    redis_client.set(f"spot:substitute:state:{cluster_id}", SubstituteState.ACTIVE.value)
    redis_client.expire(f"spot:substitute:state:{cluster_id}", handback_seconds)

    # Update metadata with promotion timestamps
    meta_raw = redis_client.get(f"spot:substitute:meta:{cluster_id}")
    if meta_raw:
        meta = json.loads(meta_raw.decode("utf-8") if isinstance(meta_raw, bytes) else meta_raw)
        meta["promoted_at"] = datetime.utcnow().isoformat()
        meta["handback_at"] = handback_at.isoformat()
        redis_client.set(f"spot:substitute:meta:{cluster_id}", json.dumps(meta))
        redis_client.expire(f"spot:substitute:meta:{cluster_id}", handback_seconds)


def select_substitute_candidates(
    target_instance_type: str,
    target_az: str,
    pool_ranking_service,
    region: str,
    optimization_mode: str
) -> list:
    """
    Select the best substitute candidates for a target node.

    For NO_DOWNTIME_FIRST mode:
      → Use on-demand instance in different AZ (same type, guaranteed capacity)

    For BALANCED/COST_FIRST mode:
      → Use ML pool ranking to find cheapest compatible spot pool in different AZ
      → Fallback: use family mapping if ML ranking unavailable

    Args:
        target_instance_type: Source node's instance type (e.g. "m5.large")
        target_az:            Source node's AZ (substitute must be in different AZ)
        pool_ranking_service: PoolRankingService instance (or None)
        region:               AWS region
        optimization_mode:    "COST_FIRST" | "BALANCED" | "NO_DOWNTIME_FIRST"

    Returns:
        List of candidate dicts (up to MAX_CANDIDATES):
        [{"instance_type": "c5.large", "az": "ap-south-1b", "lifecycle": "spot"}, ...]
    """
    candidates = []

    if optimization_mode == "NO_DOWNTIME_FIRST":
        # On-demand: same type, different AZ
        az_suffixes = ["a", "b", "c", "d"]
        for suffix in az_suffixes:
            candidate_az = f"{region}{suffix}"
            if candidate_az != target_az:
                candidates.append({
                    "instance_type": target_instance_type,
                    "az": candidate_az,
                    "lifecycle": "on-demand"
                })
                if len(candidates) >= MAX_CANDIDATES:
                    break
    else:
        # Spot: ML-ranked cheapest compatible pool in different AZ
        specs = INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
        target_vcpu, target_mem = specs

        if pool_ranking_service:
            try:
                ranked = pool_ranking_service.rank_pools_for_size(
                    vcpu=target_vcpu, memory_gb=float(target_mem),
                    region=region, limit=MAX_CANDIDATES * 4
                )
                seen_azs = set()
                for scored_pool in ranked:
                    p = scored_pool.pool
                    if p.az != target_az and p.az not in seen_azs:
                        candidates.append({
                            "instance_type": p.instance_type,
                            "az": p.az,
                            "lifecycle": "spot",
                            "spot_price": p.spot_price,
                            "risk_score": round(scored_pool.risk_probability, 3),
                        })
                        seen_azs.add(p.az)
                        if len(candidates) >= MAX_CANDIDATES:
                            break
            except Exception:
                pass

        # Fallback: family-based alternative if ML ranking failed
        if not candidates:
            family = target_instance_type.split(".")[0]
            size = target_instance_type.split(".", 1)[-1] if "." in target_instance_type else "large"
            alt_families = {"m5": ["m6i", "c5"], "c5": ["c6i", "m5"], "r5": ["r6i", "m5"]}.get(family, ["m5", "c5"])
            for alt in alt_families[:MAX_CANDIDATES]:
                for suffix in ["a", "b", "c"]:
                    candidate_az = f"{region}{suffix}"
                    if candidate_az != target_az:
                        candidates.append({
                            "instance_type": f"{alt}.{size}",
                            "az": candidate_az,
                            "lifecycle": "spot"
                        })
                        break

    return candidates[:MAX_CANDIDATES]
