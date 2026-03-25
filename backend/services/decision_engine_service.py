"""
Decision Engine Service — Unified Facade
=========================================

Orchestrates calls to PoolRankingService, BlacklistService, DiversityEnforcer,
and dry-run validation to provide a single API for pool selection.

Methods:
    rank_for_node()          — Ranked pools for a specific node
    rank_for_template()      — Ranked pools for a template
    report_termination()     — Global blacklist on interruption
    report_launch_failure()  — Track failures, auto-blacklist on threshold
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from redis import Redis
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.services.pool_ranking_service import PoolRankingService, NodeTemplate, ScoredPool
from backend.services.blacklist_service import BlacklistService


# ── Configuration ────────────────────────────────────────────────────────────
FAILURE_THRESHOLD = 3          # Auto-blacklist after this many failures in 24h
LAUNCH_FAILURE_WINDOW_HOURS = 24  # Rolling window for counting launch failures (sorted set expiry only)
                                   # NOT a blacklist duration — all blacklisting goes through
                                   # blacklist_pool_tiered() with per-severity explicit TTLs.
DRY_RUN_CACHE_TTL = 300        # 5 minutes
RANKING_CACHE_TTL = 3600       # 1 hour


def _profile_hash(min_vcpu: int, min_memory: int,
                  families: Optional[List[str]],
                  azs: Optional[List[str]]) -> str:
    """Generate a deterministic hash for a resource profile."""
    fam = sorted(families) if families else []
    az_list = sorted(azs) if azs else []
    raw = f"{min_vcpu}:{min_memory}:{fam}:{az_list}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


class DecisionEngineService:
    """
    Unified facade for pool selection decisions.

    Wraps existing PoolRankingService + BlacklistService + DiversityEnforcer
    and adds: per-profile caching, cluster_pools diversification, and
    launch failure tracking with auto-blacklisting.
    """

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.ranking_service = PoolRankingService(db, redis)
        self.blacklist_service = BlacklistService(redis)

    # ────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ────────────────────────────────────────────────────────────────────────

    def rank_for_node(
        self,
        cluster_id: str,
        node_name: str,
        limit: int = 10,
        diversify: bool = False,
    ) -> List[Dict]:
        """
        Return top ranked pools for a specific node.

        Steps:
        1. Fetch node details from DB (instance type, AZ, region).
        2. Determine minimum resource requirements.
        3. Build profile hash and check Redis cache.
        4. If miss, call PoolRankingService.rank_pools_for_size().
        5. Apply blacklist filter.
        6. Apply diversification filter (if enabled).
        7. Return top `limit` pools.
        """
        from backend.models.instance import Instance
        from backend.models.cluster import Cluster

        # 1. Fetch node details
        instance = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.node_name == node_name,
            Instance.state == "running",
        ).first()

        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not instance or not cluster:
            logger.warning(
                f"[DE] rank_for_node: node {node_name} or cluster {cluster_id} not found"
            )
            return []

        region = cluster.region or "ap-south-1"

        # 2. Determine min requirements from instance catalog
        from backend.services.dynamic_instance_helpers import _estimate_vcpu, _estimate_memory_gb
        catalog = self.ranking_service.instance_catalog
        inst_specs = catalog.get(instance.instance_type, {})
        # Use heuristic estimators for unknowns — prevents 2 vCPU/4 GB defaults
        # being used for large nodes (e.g. m5.8xlarge = 32 vCPU/128 GB) not in catalog.
        min_vcpu = inst_specs.get("vcpu") or _estimate_vcpu(instance.instance_type)
        min_memory = inst_specs.get("memory_gb") or _estimate_memory_gb(instance.instance_type)

        # 3. Check per-profile cache
        ph = _profile_hash(min_vcpu, int(min_memory), None, None)
        cache_key = f"pool_rankings:{region}:{ph}"
        cached = self._get_cached_rankings(cache_key)

        if cached:
            pools = cached
        else:
            # 4. Call underlying ML pipeline
            scored = self.ranking_service.rank_pools_for_size(
                vcpu=min_vcpu,
                memory_gb=min_memory,
                region=region,
                limit=limit * 2,  # Over-fetch to allow filtering
            )
            pools = [self._scored_to_dict(p) for p in scored]
            self._set_cached_rankings(cache_key, pools)

        # 5. Apply blacklist filter
        pools = self._apply_blacklist(pools, region)

        # 6. Apply diversification
        if diversify:
            pools = self._apply_diversification(pools, cluster_id)

        # 7. Trim to limit
        return pools[:limit]

    def rank_for_template(
        self,
        cluster_id: str,
        template: Dict,
        limit: int = 10,
        diversify: bool = False,
    ) -> List[Dict]:
        """
        Return top ranked pools for a given template specification.

        Template dict should contain: min_vcpu, min_memory, families, allowed_azs.
        """
        from backend.models.cluster import Cluster

        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return []

        region = cluster.region or "ap-south-1"
        min_vcpu = template.get("min_vcpu", 2)
        min_memory = template.get("min_memory", 4)
        families = template.get("families")
        azs = template.get("allowed_azs")

        ph = _profile_hash(min_vcpu, int(min_memory), families, azs)
        cache_key = f"pool_rankings:{region}:{ph}"
        cached = self._get_cached_rankings(cache_key)

        if cached:
            pools = cached
        else:
            scored = self.ranking_service.rank_pools_for_size(
                vcpu=min_vcpu,
                memory_gb=min_memory,
                region=region,
                allowed_families=families,
                limit=limit * 2,
            )
            pools = [self._scored_to_dict(p) for p in scored]
            self._set_cached_rankings(cache_key, pools)

        pools = self._apply_blacklist(pools, region)
        if diversify:
            pools = self._apply_diversification(pools, cluster_id)
        return pools[:limit]

    def report_termination(self, pool_key: str, region: str = "ap-south-1") -> Dict:
        """
        Report a spot interruption — globally blacklist the pool.

        Args:
            pool_key: "instance_type:az" (e.g., "m5.xlarge:ap-south-1a")
            region: AWS region
        """
        parts = pool_key.split(":")
        if len(parts) != 2:
            return {"status": "error", "message": "Invalid pool_key format"}

        instance_type, az = parts

        # Use tiered (explicit-TTL) blacklist with 15-min window for ITN events.
        # Spot capacity typically recovers in minutes; a 24-h exponential blackout
        # would cascade-blacklist all pools after a wave of simultaneous ITNs.
        result = self.blacklist_service.blacklist_pool_tiered(
            instance_type=instance_type,
            az=az,
            region=region,
            reason="spot_interruption",
            ttl_hours=0.25,  # 15 minutes — matches event_monitor.py TERMINATION_BLACKLIST_HOURS
        )

        # Track in pool_failures sorted set; TTL matches the 15-min blacklist window
        fail_key = f"pool_failures:{pool_key}"
        self.redis.zadd(fail_key, {str(datetime.utcnow().timestamp()): datetime.utcnow().timestamp()})
        self.redis.expire(fail_key, 900)  # 15 min — was 86400 (24h)

        logger.info(f"[DE] report_termination: blacklisted {pool_key}")
        return {"status": "ok", "blacklist": result}

    def report_launch_failure(
        self,
        cluster_id: str,
        pool_key: str,
        reason: str = "launch_failure",
        region: str = "ap-south-1",
    ) -> Dict:
        """
        Report a launch failure. Auto-blacklist if threshold exceeded.
        """
        fail_key = f"pool_failures:{pool_key}"
        now_ts = datetime.utcnow().timestamp()
        self.redis.zadd(fail_key, {str(now_ts): now_ts})
        self.redis.expire(fail_key, 86400)

        # Count failures in last 24h
        cutoff = now_ts - 86400
        self.redis.zremrangebyscore(fail_key, 0, cutoff)
        failure_count = self.redis.zcard(fail_key)

        result = {"status": "ok", "failure_count": failure_count}

        if failure_count >= FAILURE_THRESHOLD:
            parts = pool_key.split(":")
            if len(parts) == 2:
                instance_type, az = parts
                bl = self.blacklist_service.blacklist_pool_tiered(
                    instance_type=instance_type,
                    az=az,
                    region=region,
                    reason=f"launch_failure_x{failure_count}",
                    ttl_hours=12 if failure_count >= 5 else 6,
                )
                result["blacklisted"] = True
                result["blacklist"] = bl
                logger.warning(
                    f"[DE] Auto-blacklisted {pool_key} after {failure_count} failures"
                )

        return result

    def get_blacklist(self, region: str = "ap-south-1") -> List[Dict]:
        """Return all currently blacklisted pools for a region."""
        return self.blacklist_service.get_blacklist_status(region)

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ────────────────────────────────────────────────────────────────────────

    def _scored_to_dict(self, p: ScoredPool) -> Dict:
        return {
            "instance_type": p.pool.instance_type,
            "az": p.pool.az,
            "vcpu": p.pool.vcpu,
            "memory_gb": p.pool.memory_gb,
            "spot_price": p.pool.spot_price,
            "ondemand_price": p.pool.ondemand_price,
            "predicted_savings": p.predicted_savings,
            "risk_probability": p.risk_probability,
            "ml_score": p.ml_score,
            "rank": p.rank,
            "is_flagged": p.is_flagged,
            "pool_key": f"{p.pool.instance_type}:{p.pool.az}",
        }

    def _get_cached_rankings(self, cache_key: str) -> Optional[List[Dict]]:
        try:
            raw = self.redis.get(cache_key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _set_cached_rankings(self, cache_key: str, pools: List[Dict]):
        try:
            self.redis.setex(cache_key, RANKING_CACHE_TTL, json.dumps(pools))
        except Exception as e:
            logger.warning(f"[DE] Failed to cache rankings: {e}")

    def _apply_blacklist(self, pools: List[Dict], region: str) -> List[Dict]:
        """Remove blacklisted pools from results."""
        filtered = []
        for p in pools:
            bl, _ = self.blacklist_service.is_blacklisted(
                p["instance_type"], p["az"], region
            )
            if not bl:
                filtered.append(p)
        return filtered

    def _apply_diversification(self, pools: List[Dict], cluster_id: str) -> List[Dict]:
        """Remove pools already in use by the cluster."""
        cluster_pools_key = f"cluster_pools:{cluster_id}"
        try:
            in_use = self.redis.smembers(cluster_pools_key)
            if not in_use:
                return pools
            in_use_str = {m.decode() if isinstance(m, bytes) else m for m in in_use}
            return [p for p in pools if p.get("pool_key") not in in_use_str]
        except Exception:
            return pools
