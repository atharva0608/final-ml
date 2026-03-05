"""
Substitute Manager Service

Manages substitute instance lifecycle for zero-downtime spot replacements.
Supports node-aware substitute deployment with state machine management.

State Flow:
  IDLE → PREWARMING → READY → ACTIVE → RELEASING → IDLE

Author: Spot Optimizer Platform
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.redis_client import get_redis_client
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.services.workload_inspector import WorkloadInspector, NodeStatus
from backend.services.resource_pricing_service import ResourcePricingService

logger = logging.getLogger(__name__)

# Compact vcpu/memory lookup for common instance types used during substitute selection.
# Used to call PoolRankingService.rank_pools_for_size() with the right size constraints.
_INSTANCE_VCPU_MEM: dict = {
    "t3.nano": (2, 0.5), "t3.micro": (2, 1), "t3.small": (2, 2), "t3.medium": (2, 4),
    "t3.large": (2, 8), "t3.xlarge": (4, 16), "t3.2xlarge": (8, 32),
    "t3a.micro": (2, 1), "t3a.small": (2, 2), "t3a.medium": (2, 4), "t3a.large": (2, 8),
    "t3a.xlarge": (4, 16), "t3a.2xlarge": (8, 32),
    "t4g.nano": (2, 0.5), "t4g.micro": (2, 1), "t4g.small": (2, 2), "t4g.medium": (2, 4),
    "t4g.large": (2, 8), "t4g.xlarge": (4, 16), "t4g.2xlarge": (8, 32),
    "m5.large": (2, 8), "m5.xlarge": (4, 16), "m5.2xlarge": (8, 32), "m5.4xlarge": (16, 64),
    "m5a.large": (2, 8), "m5a.xlarge": (4, 16), "m5a.2xlarge": (8, 32),
    "m6i.large": (2, 8), "m6i.xlarge": (4, 16), "m6i.2xlarge": (8, 32),
    "m6a.large": (2, 8), "m6a.xlarge": (4, 16), "m6a.2xlarge": (8, 32),
    "m6g.medium": (1, 4), "m6g.large": (2, 8), "m6g.xlarge": (4, 16), "m6g.2xlarge": (8, 32),
    "c5.large": (2, 4), "c5.xlarge": (4, 8), "c5.2xlarge": (8, 16), "c5.4xlarge": (16, 32),
    "c6i.large": (2, 4), "c6i.xlarge": (4, 8), "c6i.2xlarge": (8, 16),
    "c6a.large": (2, 4), "c6a.xlarge": (4, 8), "c6a.2xlarge": (8, 16),
    "c6g.medium": (1, 2), "c6g.large": (2, 4), "c6g.xlarge": (4, 8), "c6g.2xlarge": (8, 16),
    "r5.large": (2, 16), "r5.xlarge": (4, 32), "r5.2xlarge": (8, 64),
    "r6i.large": (2, 16), "r6i.xlarge": (4, 32), "r6i.2xlarge": (8, 64),
    "r6g.large": (2, 16), "r6g.xlarge": (4, 32), "r6g.2xlarge": (8, 64),
}


class SubstituteState(str, Enum):
    """Substitute instance lifecycle states"""
    IDLE = "IDLE"
    PREWARMING = "PREWARMING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    RELEASING = "RELEASING"


class SubstituteManager:
    """
    Manages substitute instances for zero-downtime spot replacements.

    Key Features:
    - Node-aware substitute selection (validates target node classification)
    - Mode-aware provisioning (on-demand for NO_DOWNTIME_FIRST, spot for others)
    - State machine with Redis persistence
    - DryRun validation before deployment
    - Cost drift monitoring
    - Automatic handback after 6 hours
    """

    # Configuration constants
    HANDBACK_HOURS = 6
    MAX_COST_DRIFT_PERCENT = 15
    PREWARMING_TIMEOUT_MINUTES = 5
    READY_TIMEOUT_HOURS = 1
    MAX_CANDIDATES = 3

    def __init__(self, db: Session, redis_client=None):
        """
        Initialize SubstituteManager.

        Args:
            db: SQLAlchemy database session
            redis_client: Redis client (auto-initialized if None)
        """
        self.db = db
        self.redis = redis_client or get_redis_client()
        self.workload_inspector = WorkloadInspector(redis_client)
        self.pricing_service = ResourcePricingService(db)

    # =========================================================================
    # State Management
    # =========================================================================

    def get_state(self, cluster_id: str) -> SubstituteState:
        """
        Get current substitute state for cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Current SubstituteState
        """
        state_key = f"spot:substitute:state:{cluster_id}"
        state = self.redis.get(state_key)

        if not state:
            return SubstituteState.IDLE

        return SubstituteState(state.decode("utf-8") if isinstance(state, bytes) else state)

    def _set_state(
        self,
        cluster_id: str,
        state: SubstituteState,
        metadata: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Set substitute state with optional metadata.

        Args:
            cluster_id: Cluster identifier
            state: Target SubstituteState
            metadata: Optional metadata to store alongside state
            ttl_seconds: Optional TTL for state expiry
        """
        state_key = f"spot:substitute:state:{cluster_id}"
        self.redis.set(state_key, state.value)

        if ttl_seconds:
            self.redis.expire(state_key, ttl_seconds)

        if metadata:
            meta_key = f"spot:substitute:meta:{cluster_id}"
            self.redis.set(meta_key, json.dumps(metadata))
            if ttl_seconds:
                self.redis.expire(meta_key, ttl_seconds)

        logger.info(f"Substitute state transition: cluster={cluster_id}, state={state.value}")

    def _get_metadata(self, cluster_id: str) -> Optional[Dict]:
        """
        Retrieve substitute metadata from Redis.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Metadata dict or None
        """
        meta_key = f"spot:substitute:meta:{cluster_id}"
        data = self.redis.get(meta_key)

        if not data:
            return None

        return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)

    # =========================================================================
    # Substitute Type Selection
    # =========================================================================

    def get_substitute_type(self, cluster_id: str) -> str:
        """
        Determine substitute lifecycle type based on cluster optimization mode.

        Args:
            cluster_id: Cluster identifier

        Returns:
            "on-demand" or "spot"
        """
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()

        if not cluster:
            raise ValueError(f"Cluster not found: {cluster_id}")

        # NO_DOWNTIME_FIRST → always use on-demand substitute
        if cluster.optimization_mode == "NO_DOWNTIME_FIRST":
            return "on-demand"

        # BALANCED/COST_FIRST → use spot substitute (different family+AZ for diversification)
        return "spot"

    # =========================================================================
    # Substitute Deployment
    # =========================================================================

    def deploy_substitute(
        self,
        cluster_id: str,
        target_node_name: str
    ) -> Dict:
        """
        Deploy substitute instance for target node.

        Workflow:
        1. Validate target node is STATELESS_ELIGIBLE
        2. Set state to PREWARMING
        3. Select top 3 candidates (based on mode)
        4. Validate each via DryRun API
        5. Transition to READY when validated

        Args:
            cluster_id: Cluster identifier
            target_node_name: Node to substitute

        Returns:
            {
                "success": bool,
                "state": str,
                "substitute_instance_id": str,
                "instance_type": str,
                "lifecycle": str,
                "az": str,
                "message": str
            }
        """
        # Validate cluster
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster not found: {cluster_id}")

        # Validate target node
        target_node = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.node_name == target_node_name
        ).first()

        if not target_node:
            raise ValueError(f"Target node not found: {target_node_name}")

        # Check node classification
        classifications = self.workload_inspector.get_cached_classification(cluster_id)
        classification = classifications.get(target_node_name) if classifications else None
        
        if classification != NodeStatus.STATELESS_ELIGIBLE:
            return {
                "success": False,
                "state": self.get_state(cluster_id).value,
                "message": f"Target node is {classification.value if getattr(classification, 'value', None) else classification}, must be STATELESS_ELIGIBLE"
            }

        # Set PREWARMING state
        timeout_seconds = self.PREWARMING_TIMEOUT_MINUTES * 60
        self._set_state(
            cluster_id,
            SubstituteState.PREWARMING,
            metadata={
                "target_node_name": target_node_name,
                "target_instance_id": target_node.instance_id,
                "started_at": datetime.utcnow().isoformat()
            },
            ttl_seconds=timeout_seconds
        )

        # Select candidates
        substitute_type = self.get_substitute_type(cluster_id)
        candidates = self._select_top_substitute_candidates(
            cluster,
            target_node,
            substitute_type
        )

        if not candidates:
            self._set_state(cluster_id, SubstituteState.IDLE)
            return {
                "success": False,
                "state": SubstituteState.IDLE.value,
                "message": "No valid substitute candidates found"
            }

        # Validate candidates via DryRun
        import time
        for idx, candidate in enumerate(candidates):
            if idx > 0:
                # Small backoff before retrying
                time.sleep(2)
                if self.redis:
                    self.redis.incr("spot:metrics:substitute_retry")
                logger.info(f"Retrying substitute deployment with candidate {idx+1}")
                
            valid = self._validate_candidate_dryrun(cluster, candidate)
            if valid:
                # Transition to READY
                ready_timeout = self.READY_TIMEOUT_HOURS * 3600
                self._set_state(
                    cluster_id,
                    SubstituteState.READY,
                    metadata={
                        "target_node_name": target_node_name,
                        "target_instance_id": target_node.instance_id,
                        "substitute_instance_type": candidate["instance_type"],
                        "substitute_az": candidate["az"],
                        "substitute_lifecycle": candidate["lifecycle"],
                        "validated_at": datetime.utcnow().isoformat()
                    },
                    ttl_seconds=ready_timeout
                )

                return {
                    "success": True,
                    "state": SubstituteState.READY.value,
                    "instance_type": candidate["instance_type"],
                    "lifecycle": candidate["lifecycle"],
                    "az": candidate["az"],
                    "message": "Substitute validated and ready for promotion"
                }

        # All candidates failed validation
        self._set_state(cluster_id, SubstituteState.IDLE)
        return {
            "success": False,
            "state": SubstituteState.IDLE.value,
            "message": f"All {len(candidates)} candidates failed DryRun validation"
        }

    def _select_top_substitute_candidates(
        self,
        cluster: Cluster,
        target_node: Instance,
        substitute_type: str
    ) -> List[Dict]:
        """
        Select top substitute candidates based on optimization mode.

        Args:
            cluster: Cluster model
            target_node: Instance model of target node
            substitute_type: "on-demand" or "spot"

        Returns:
            List of candidate dicts with instance_type, az, lifecycle
        """
        candidates = []
        region = cluster.region or "ap-south-1"
        target_az = target_node.availability_zone

        if substitute_type == "on-demand":
            # NO_DOWNTIME_FIRST: use same instance type in different AZ (on-demand)
            # Try region-aware AZ names first, then fall back to generic us-east-1 set
            region_prefix = region.rstrip("0123456789")
            az_suffixes = ["a", "b", "c", "d"]
            candidate_azs = [f"{region}{s}" for s in az_suffixes]
            for az in candidate_azs:
                if az != target_az:
                    candidates.append({
                        "instance_type": target_node.instance_type,
                        "az": az,
                        "lifecycle": "on-demand"
                    })
                    if len(candidates) >= self.MAX_CANDIDATES:
                        break

        else:
            # BALANCED/COST_FIRST: use ML-ranked cheapest compatible spot pool
            # Look up the target node's vcpu/memory to drive size-constrained ranking
            target_specs = _INSTANCE_VCPU_MEM.get(target_node.instance_type)
            if target_specs:
                target_vcpu, target_mem = target_specs
            else:
                # Default: assume 2 vCPU / 8 GB (m5.large equivalent)
                target_vcpu, target_mem = 2, 8

            try:
                from backend.services.pool_ranking_service import PoolRankingService
                _svc = PoolRankingService(self.db, self.redis)
                # Fetch extra candidates so we have enough after AZ filtering
                ranked = _svc.rank_pools_for_size(
                    vcpu=target_vcpu,
                    memory_gb=float(target_mem),
                    region=region,
                    limit=self.MAX_CANDIDATES * 4
                )
                seen_azs: set = set()
                for scored_pool in ranked:
                    p = scored_pool.pool
                    # Exclude same AZ and already-seen AZs for diversification
                    if p.az != target_az and p.az not in seen_azs:
                        candidates.append({
                            "instance_type": p.instance_type,
                            "az": p.az,
                            "lifecycle": "spot",
                            "spot_price": p.spot_price,
                            "risk_score": round(scored_pool.risk_probability, 3),
                        })
                        seen_azs.add(p.az)
                        if len(candidates) >= self.MAX_CANDIDATES:
                            break
            except Exception as e:
                logger.warning(
                    f"ML pool ranking failed for substitute selection "
                    f"(cluster={cluster.id}), falling back to family map: {e}"
                )

            # Fallback: ML returned nothing — use conservative family + size suffix
            if not candidates:
                family = target_node.instance_type.split(".")[0]
                size_suffix = (
                    target_node.instance_type.split(".", 1)[-1]
                    if "." in target_node.instance_type else "large"
                )
                alt_families = self._get_alternative_families(family)
                az_suffixes = ["a", "b", "c"]
                candidate_azs = [f"{region}{s}" for s in az_suffixes]
                for alt_family in alt_families[:self.MAX_CANDIDATES]:
                    for az in candidate_azs:
                        if az != target_az:
                            candidates.append({
                                "instance_type": f"{alt_family}.{size_suffix}",
                                "az": az,
                                "lifecycle": "spot"
                            })
                            break
                    if len(candidates) >= self.MAX_CANDIDATES:
                        break

        return candidates[:self.MAX_CANDIDATES]

    def _get_alternative_families(self, current_family: str) -> List[str]:
        """
        Get alternative instance families for diversification.

        Args:
            current_family: Current family (e.g., "m5")

        Returns:
            List of alternative families
        """
        # Mapping of families to alternatives (same CPU/memory ratio)
        alternatives_map = {
            "m5": ["m6i", "m5a", "m5n"],
            "m6i": ["m5", "m6a", "m5n"],
            "c5": ["c6i", "c5a", "c5n"],
            "c6i": ["c5", "c6a", "c5n"],
            "r5": ["r6i", "r5a", "r5n"],
            "r6i": ["r5", "r6a", "r5n"],
            "t3": ["t3a", "t2"],
            "t3a": ["t3", "t2"]
        }

        return alternatives_map.get(current_family, ["m5", "m6i", "c5"])

    def _validate_candidate_dryrun(
        self,
        cluster: Cluster,
        candidate: Dict
    ) -> bool:
        """
        Validate substitute candidate using EC2 DryRun API.

        Args:
            cluster: Cluster model
            candidate: Candidate dict with instance_type, az, lifecycle

        Returns:
            True if candidate is valid (DryRun succeeds)
        """
        try:
            import boto3
            from botocore.exceptions import ClientError

            ec2 = boto3.client("ec2", region_name=cluster.region)

            # Prepare RunInstances parameters
            params = {
                "InstanceType": candidate["instance_type"],
                "MinCount": 1,
                "MaxCount": 1,
                "DryRun": True,
                "Placement": {
                    "AvailabilityZone": candidate["az"]
                }
            }

            if candidate["lifecycle"] == "spot":
                params["InstanceMarketOptions"] = {
                    "MarketType": "spot"
                }

            # Execute DryRun
            ec2.run_instances(**params)

            # If we reach here, DryRun passed (shouldn't happen, DryRun always raises)
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            # DryRunOperation means the request would succeed
            if error_code == "DryRunOperation":
                logger.info(
                    f"DryRun validation passed: {candidate['instance_type']} "
                    f"in {candidate['az']} ({candidate['lifecycle']})"
                )
                return True

            # Any other error means validation failed
            logger.warning(
                f"DryRun validation failed: {candidate['instance_type']} "
                f"in {candidate['az']} - {error_code}"
            )
            return False

        except Exception as e:
            logger.error(f"DryRun validation error: {str(e)}")
            return False

    # =========================================================================
    # Substitute Promotion & Release
    # =========================================================================

    def promote_substitute(self, cluster_id: str) -> Dict:
        """
        Promote substitute from READY to ACTIVE state.

        Args:
            cluster_id: Cluster identifier

        Returns:
            {
                "success": bool,
                "state": str,
                "handback_at": str (ISO timestamp),
                "message": str
            }
        """
        current_state = self.get_state(cluster_id)

        if current_state != SubstituteState.READY:
            return {
                "success": False,
                "state": current_state.value,
                "message": f"Cannot promote from {current_state.value}, must be READY"
            }

        # Set ACTIVE state with handback timer
        handback_seconds = self.HANDBACK_HOURS * 3600
        handback_at = datetime.utcnow() + timedelta(hours=self.HANDBACK_HOURS)

        metadata = self._get_metadata(cluster_id) or {}
        metadata["promoted_at"] = datetime.utcnow().isoformat()
        metadata["handback_at"] = handback_at.isoformat()

        self._set_state(
            cluster_id,
            SubstituteState.ACTIVE,
            metadata=metadata,
            ttl_seconds=handback_seconds
        )

        # ── SUBSTITUTE COOLDOWN WIRING (GAP 4 FIX) ───────────────────
        try:
            from backend.services.cooldown_controller import CooldownController
            CooldownController(self.redis).record_substitute_action(cluster_id)
            logger.info(f"Recorded substitute cooldown for cluster {cluster_id}")
        except Exception as e:
            logger.error(f"Failed to record substitute cooldown: {e}")

        # ── WARM SPARE: kick off replacement spare immediately ─────────
        # Schedule a single-cluster warm spare task to provision the next spare
        try:
            from backend.workers.tasks.maintain_warm_spare_worker import maintain_warm_spare_single_cluster
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            region = cluster.region if cluster else "ap-south-1"
            maintain_warm_spare_single_cluster.apply_async(
                args=[cluster_id, region], countdown=10
            )
            logger.info(f"Scheduled replacement warm spare for cluster {cluster_id}")
        except Exception as e:
            logger.warning(f"Could not schedule replacement spare task: {e}")

        return {
            "success": True,
            "state": SubstituteState.ACTIVE.value,
            "handback_at": handback_at.isoformat(),
            "message": f"Substitute promoted to ACTIVE, will handback in {self.HANDBACK_HOURS}h"
        }

    def release_substitute(self, cluster_id: str) -> Dict:
        """
        Release substitute instance (ACTIVE → RELEASING → IDLE).

        Args:
            cluster_id: Cluster identifier

        Returns:
            {
                "success": bool,
                "state": str,
                "message": str
            }
        """
        current_state = self.get_state(cluster_id)

        if current_state != SubstituteState.ACTIVE:
            return {
                "success": False,
                "state": current_state.value,
                "message": f"Cannot release from {current_state.value}, must be ACTIVE"
            }

        # Set RELEASING state (short TTL for cleanup)
        self._set_state(
            cluster_id,
            SubstituteState.RELEASING,
            metadata={"released_at": datetime.utcnow().isoformat()},
            ttl_seconds=60
        )

        # TODO: Trigger actual EC2 termination here (integrate with AWS service)

        # Transition to IDLE
        self._set_state(cluster_id, SubstituteState.IDLE)

        return {
            "success": True,
            "state": SubstituteState.IDLE.value,
            "message": "Substitute released successfully"
        }

    # =========================================================================
    # Cost Drift Monitoring
    # =========================================================================

    def check_cost_drift(self, cluster_id: str) -> Optional[Dict]:
        """
        Check if substitute cost has drifted beyond threshold.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Dict with drift info if exceeds threshold, None otherwise
            {
                "drift_percent": float,
                "threshold_percent": int,
                "original_cost": float,
                "current_cost": float,
                "recommendation": str
            }
        """
        metadata = self._get_metadata(cluster_id)
        if not metadata or "substitute_instance_type" not in metadata:
            return None

        substitute_type = metadata["substitute_instance_type"]
        substitute_az = metadata["substitute_az"]
        substitute_lifecycle = metadata["substitute_lifecycle"]

        # Get current pricing
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return None

        current_price = self.pricing_service.get_instance_price(
            instance_type=substitute_type,
            region=cluster.region,
            lifecycle=substitute_lifecycle,
            availability_zone=substitute_az
        )

        # Get original price (if stored)
        original_price = metadata.get("original_price")
        if not original_price:
            # Store current price as baseline
            metadata["original_price"] = current_price
            self._set_state(cluster_id, self.get_state(cluster_id), metadata=metadata)
            return None

        # Calculate drift
        drift_percent = ((current_price - original_price) / original_price) * 100

        if drift_percent > self.MAX_COST_DRIFT_PERCENT:
            return {
                "drift_percent": round(drift_percent, 2),
                "threshold_percent": self.MAX_COST_DRIFT_PERCENT,
                "original_cost": original_price,
                "current_cost": current_price,
                "recommendation": "Consider replacing substitute with cheaper alternative"
            }

        return None

    # =========================================================================
    # Warm Spare — Persistent 24x7 compatible substitute
    # =========================================================================

    def find_max_node_specs(self, cluster_id: str) -> Optional[Dict]:
        """
        Find the largest node in the cluster (highest vCPU × memory_gb).

        Returns dict with instance_type, vcpu, memory_gb, instance_id.
        A substitute sized for this node can absorb ANY node drain in the cluster.
        """
        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == "running"
        ).all()

        if not instances:
            return None

        best = None
        best_score = 0
        for inst in instances:
            specs = _INSTANCE_VCPU_MEM.get(inst.instance_type)
            if not specs:
                continue
            vcpu, mem = specs
            score = vcpu * mem
            if score > best_score:
                best_score = score
                best = {
                    "instance_type": inst.instance_type,
                    "vcpu": vcpu,
                    "memory_gb": float(mem),
                    "instance_id": inst.instance_id,
                }

        return best

    def ensure_warm_spare(self, cluster_id: str, region: str) -> Dict:
        """
        Ensure at least 1 warm spare is always running 24x7.

        Logic:
          - Find the largest node in the cluster
          - Find the cheapest spot pool that can absorb that node's specs
          - If no spare exists → PREWARMING → READY (no TTL, stays forever)
          - If spare is ACTIVE (in use) → kick off replacement spare immediately
          - If max-node specs grew → re-provision with larger spare
          - READY state has no TTL — spare runs until used or specs change
        """
        state = self.get_state(cluster_id)
        metadata = self._get_metadata(cluster_id) or {}

        # ── Find the biggest node ──────────────────────────────────────────────
        max_node = self.find_max_node_specs(cluster_id)
        if not max_node:
            return {"status": "no_nodes", "cluster_id": cluster_id}

        # ── Find cheapest spot pool that fits those specs ──────────────────────
        try:
            from backend.services.pool_ranking_service import PoolRankingService
            _svc = PoolRankingService(self.db, self.redis)
            ranked = _svc.rank_pools_for_size(
                vcpu=max_node["vcpu"],
                memory_gb=max_node["memory_gb"],
                region=region,
                limit=5
            )
            if not ranked:
                return {"status": "no_pools_found", "cluster_id": cluster_id, "max_node": max_node}
            best = ranked[0]
            best_pool_data = {
                "instance_type": best.pool.instance_type,
                "az": best.pool.az,
                "spot_price_hourly": round(best.pool.spot_price, 4),
                "risk_score": round(best.risk_probability, 3),
                "monthly_cost": round(best.pool.spot_price * 720, 2),
            }
        except Exception as e:
            logger.error(f"Pool ranking failed for warm spare cluster={cluster_id}: {e}")
            return {"status": "pool_ranking_failed", "cluster_id": cluster_id, "error": str(e)}

        # ── Check if re-provisioning is needed ────────────────────────────────
        stored_vcpu = metadata.get("target_vcpu", 0)
        stored_mem = metadata.get("target_memory_gb", 0)
        specs_grew = (max_node["vcpu"] > stored_vcpu or max_node["memory_gb"] > stored_mem)

        if state == SubstituteState.PREWARMING:
            # Already warming up — nothing to do
            return {"status": "already_prewarming", "cluster_id": cluster_id}

        if state == SubstituteState.READY and not specs_grew:
            # Healthy spare, still compatible — nothing to do
            return {
                "status": "spare_ready",
                "cluster_id": cluster_id,
                "spare_instance_type": metadata.get("substitute_instance_type"),
                "spare_az": metadata.get("substitute_az"),
                "monthly_cost": metadata.get("monthly_cost"),
            }

        # Need to provision (new, replacement after IN_USE, or spec upgrade)
        if state == SubstituteState.ACTIVE:
            action = "replacement_spare"
            # Also store next-spare key so UI can show "replacement prewarming"
            next_key = f"spot:substitute:next_spare:{cluster_id}"
            self.redis.set(next_key, json.dumps({
                "state": "PREWARMING",
                "instance_type": best_pool_data["instance_type"],
                "az": best_pool_data["az"],
                "started_at": datetime.utcnow().isoformat(),
            }))
            # Main state stays ACTIVE — don't overwrite
            logger.info(f"[warm-spare] Replacement spare prewarming for cluster {cluster_id}")
            return {"status": "replacement_prewarming", "action": action, "cluster_id": cluster_id}
        elif specs_grew:
            action = "spec_upgrade"
        else:
            action = "initial_provision"

        spare_meta = {
            "is_warm_spare": True,
            "target_node_instance_type": max_node["instance_type"],
            "target_vcpu": max_node["vcpu"],
            "target_memory_gb": max_node["memory_gb"],
            "substitute_instance_type": best_pool_data["instance_type"],
            "substitute_az": best_pool_data["az"],
            "substitute_lifecycle": "spot",
            "spot_price_hourly": best_pool_data["spot_price_hourly"],
            "monthly_cost": best_pool_data["monthly_cost"],
            "risk_score": best_pool_data["risk_score"],
            "compatible_with": f"Any node ≤ {max_node['vcpu']} vCPU / {max_node['memory_gb']} GB",
            "started_at": datetime.utcnow().isoformat(),
            "validated_at": datetime.utcnow().isoformat(),
        }

        # PREWARMING (brief) → READY with no TTL (stays forever)
        self._set_state(cluster_id, SubstituteState.PREWARMING, metadata=spare_meta)
        self._set_state(cluster_id, SubstituteState.READY, metadata=spare_meta, ttl_seconds=None)

        logger.info(
            f"[warm-spare] {action} for cluster {cluster_id}: "
            f"{best_pool_data['instance_type']} in {best_pool_data['az']} "
            f"@ ${best_pool_data['spot_price_hourly']}/hr "
            f"(${best_pool_data['monthly_cost']}/mo)"
        )
        return {
            "status": "provisioned",
            "action": action,
            "cluster_id": cluster_id,
            "spare_instance_type": best_pool_data["instance_type"],
            "spare_az": best_pool_data["az"],
            "monthly_cost": best_pool_data["monthly_cost"],
        }

    # =========================================================================
    # Status & Reconciliation
    # =========================================================================

    def get_substitute_status(self, cluster_id: str) -> Optional[Dict]:
        """
        Get complete substitute status for cluster.

        Returns:
            Status dict (always returns for READY/ACTIVE/PREWARMING warm spare,
            None only for true IDLE with no spare configured)
        """
        state = self.get_state(cluster_id)
        metadata = self._get_metadata(cluster_id) or {}

        if state == SubstituteState.IDLE and not metadata.get("is_warm_spare"):
            return None

        status = {
            "cluster_id": cluster_id,
            "state": state.value,
            "is_warm_spare": metadata.get("is_warm_spare", False),
            "substitute_instance_type": metadata.get("substitute_instance_type"),
            "substitute_az": metadata.get("substitute_az"),
            "substitute_lifecycle": metadata.get("substitute_lifecycle", "spot"),
            "spot_price_hourly": metadata.get("spot_price_hourly"),
            "monthly_cost": metadata.get("monthly_cost"),
            "target_vcpu": metadata.get("target_vcpu"),
            "target_memory_gb": metadata.get("target_memory_gb"),
            "target_node_instance_type": metadata.get("target_node_instance_type"),
            "compatible_with": metadata.get("compatible_with"),
            "risk_score": metadata.get("risk_score"),
            "started_at": metadata.get("started_at"),
            "validated_at": metadata.get("validated_at"),
            "promoted_at": metadata.get("promoted_at"),
            "handback_at": metadata.get("handback_at"),
            # Legacy fields
            "target_node_name": metadata.get("target_node_name"),
        }

        # Check for replacement spare being prewarmed (when primary is ACTIVE)
        if state == SubstituteState.ACTIVE:
            next_key = f"spot:substitute:next_spare:{cluster_id}"
            next_data = self.redis.get(next_key)
            if next_data:
                status["next_spare"] = json.loads(next_data.decode("utf-8") if isinstance(next_data, bytes) else next_data)
            drift = self.check_cost_drift(cluster_id)
            if drift:
                status["cost_drift"] = drift

        return status

    def reconcile_stuck_substitutes(self) -> Dict:
        """
        Reconcile stuck substitutes (called by Celery beat scheduler).

        Handles:
        - PREWARMING timeout (>5min → IDLE)
        - READY timeout (>1hr → IDLE)
        - ACTIVE handback (>6hr → RELEASING → IDLE)

        Returns:
            {
                "reconciled_count": int,
                "transitions": List[Dict]
            }
        """
        transitions = []

        # Scan all substitute keys in Redis
        pattern = "spot:substitute:state:*"
        for key in self.redis.scan_iter(match=pattern):
            cluster_id = key.decode("utf-8").split(":")[-1]
            state = self.get_state(cluster_id)
            metadata = self._get_metadata(cluster_id) or {}

            # Handle timeouts
            if state == SubstituteState.PREWARMING:
                started_at = metadata.get("started_at")
                if started_at:
                    started = datetime.fromisoformat(started_at)
                    if datetime.utcnow() - started > timedelta(minutes=self.PREWARMING_TIMEOUT_MINUTES):
                        self._set_state(cluster_id, SubstituteState.IDLE)
                        transitions.append({
                            "cluster_id": cluster_id,
                            "from": SubstituteState.PREWARMING.value,
                            "to": SubstituteState.IDLE.value,
                            "reason": "Prewarming timeout"
                        })

            elif state == SubstituteState.READY:
                # Warm spare READY state has no timeout — it stays running 24x7
                if metadata.get("is_warm_spare"):
                    continue
                validated_at = metadata.get("validated_at")
                if validated_at:
                    validated = datetime.fromisoformat(validated_at)
                    if datetime.utcnow() - validated > timedelta(hours=self.READY_TIMEOUT_HOURS):
                        self._set_state(cluster_id, SubstituteState.IDLE)
                        transitions.append({
                            "cluster_id": cluster_id,
                            "from": SubstituteState.READY.value,
                            "to": SubstituteState.IDLE.value,
                            "reason": "Ready timeout (not promoted)"
                        })

            elif state == SubstituteState.ACTIVE:
                handback_at = metadata.get("handback_at")
                if handback_at:
                    handback = datetime.fromisoformat(handback_at)
                    if datetime.utcnow() >= handback:
                        self.release_substitute(cluster_id)
                        transitions.append({
                            "cluster_id": cluster_id,
                            "from": SubstituteState.ACTIVE.value,
                            "to": SubstituteState.IDLE.value,
                            "reason": "Handback timer expired"
                        })

        return {
            "reconciled_count": len(transitions),
            "transitions": transitions
        }
