"""
Pool Ranking Service - ASCPAi System A: Pool Selection Pipeline

8-step filtering and ranking pipeline:
1. Node Template Filtering - User-defined requirements (arch, vCPU, memory, families, sizes, AZs)
2. AZ Filtering - User AZ preferences
3. Spot Advisor Filter - AWS Spot Advisor frequency rank filtering
4. Global Blacklist Check - Redis-based risky pool flags from System B
5. Capacity Check - AWS API real-time capacity validation
6. Price Fetch - AWS Pricing API for spot/on-demand prices
7. ML Model Scoring - ONNX model inference (classifier → risk, regressor → savings)
8. Final Ranking & Caching - Deduplicate by instance type, sort by composite score, cache in Redis

Outputs: Ranked list of diverse instance pools with predicted savings, risk probability, and composite scores.
"""

import os
import uuid
try:
    import onnxruntime as ort
except ImportError:
    ort = None
import numpy as np
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from redis import Redis
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.services.ml_feature_service import MLFeatureService
from backend.core.logger import logger

# ── Two-tier global cache constants ──────────────────────────────────────────
GLOBAL_CACHE_TTL = 65 * 60    # 65 minutes — balances freshness vs compute cost
GLOBAL_CACHE_LIMIT = 1500     # Top 1500 safest pools cached per region (no template filter)


@dataclass
class NodeTemplate:
    """User-defined node filtering requirements."""
    architecture: List[str]  # ["amd64", "arm64"]
    vcpu_range: Tuple[int, int]  # (min, max)
    memory_range: Tuple[int, int]  # (min_gb, max_gb)
    allowed_families: Optional[List[str]] = None  # ["m5", "c5", "r5"]
    allowed_sizes: Optional[List[str]] = None  # ["xlarge", "2xlarge"]
    allowed_azs: Optional[List[str]] = None  # ["aps1-az1", "aps1-az2"]
    excluded_instance_types: Optional[List[str]] = None  # ["m5.metal", "c5.24xlarge"]
    source_od_price: Optional[float] = None  # Source node's OD hourly price — used as price ceiling


@dataclass
class InstancePool:
    """Candidate instance pool (instance_type + AZ combination)."""
    instance_type: str
    az: str
    architecture: str
    vcpu: int
    memory_gb: float
    spot_price: float
    ondemand_price: float
    spot_advisor_rank: int  # 0-5 (0=<5% interruption, 5=>20%)
    has_capacity: bool = True
    capacity_uncertain: bool = False  # True when capacity check timed out — pool included but flagged


@dataclass
class ScoredPool:
    """Instance pool with ML scores and final ranking."""
    pool: InstancePool
    predicted_savings: float  # From regressor_6.onnx (0-1 scale, higher = more savings vs on-demand)
    risk_probability: float  # From classifier_6.onnx (0-1 scale, lower = safer)
    ml_score: float  # Final composite score: (savings × 0.4) - (risk × 0.6)
    is_flagged: bool  # Flagged by System B (global blacklist)
    rank: int  # Final ranking position
    timestamp: datetime
    capacity_status: Optional[str] = None  # "validated", "unavailable", "unvalidated"
    capacity_validated_at: Optional[str] = None  # ISO timestamp
    requesting_cluster_id: Optional[str] = None  # Cluster that requested this ranking
    # Legacy aliases for backward compatibility
    @property
    def savings_pct(self):
        return self.predicted_savings
    @property
    def cost_estimate(self):
        return self.risk_probability


class PoolRankingService:
    """
    ASCPAi Pool Selection Pipeline - System A.

    Orchestrates 8-step filtering and scoring to provide ranked pool recommendations.
    """

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.feature_service = MLFeatureService(db)

        # Load risk threshold config
        self.risk_threshold = self._load_risk_config()

        # Load ONNX models
        try:
            self.classifier_session = ort.InferenceSession(
                "ml_model/model/classifier_6.onnx",
                providers=['CPUExecutionProvider']
            )
            self.regressor_session = ort.InferenceSession(
                "ml_model/model/regressor_6.onnx",
                providers=['CPUExecutionProvider']
            )
            logger.debug("ONNX models loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ONNX models: {e}")
            self.classifier_session = None
            self.regressor_session = None

        # Load instance catalog (AWS instance type specs)
        self.instance_catalog = self._load_instance_catalog()

    def _load_risk_config(self):
        """
        Load ML risk threshold from config file.

        Config file: ml_model/risk_threshold.json
        - optimal_threshold: F1-optimized classifier threshold (default 0.35)
        """
        config_path = os.path.join("ml_model", "risk_threshold.json")
        try:
            with open(config_path) as f:
                config = json.load(f)
            threshold = config.get("optimal_threshold", 0.35)
            logger.debug(f"Risk config loaded: threshold={threshold}")
            return threshold
        except FileNotFoundError:
            logger.warning(f"Risk config not found at {config_path}, using defaults")
            return 0.35
        except Exception as e:
            logger.error(f"Failed to load risk config: {e}, using defaults")
            return 0.35

    def _load_instance_catalog(self) -> Dict[str, Dict]:
        """
        Load AWS instance catalog with specs (vCPU, memory, architecture).

        Priority:
          1. InstanceCatalog DB table (populated nightly by instance_catalog_worker)
          2. Hardcoded fallback dict (used only on first boot before worker runs)
        """
        # Try DB-backed catalog first
        from backend.services.dynamic_instance_helpers import load_instance_catalog_from_db

        db_catalog = load_instance_catalog_from_db(self.db)
        if db_catalog:
            return db_catalog

        # ── Hardcoded fallback (used until nightly worker populates DB) ───
        # WARNING (Task 4.7): Boot-time fallback only. In production, the
        # instance_catalog_worker populates the DB within the first scheduled run.
        logger.warning(
            "Using hardcoded instance catalog (DB catalog empty). "
            "This is expected only on first boot before the nightly worker runs."
        )
        return {
            "t3.nano":    {"vcpu": 2, "memory_gb": 0.5,  "architecture": "amd64"},
            "t3.micro":   {"vcpu": 2, "memory_gb": 1,    "architecture": "amd64"},
            "t3.small":   {"vcpu": 2, "memory_gb": 2,    "architecture": "amd64"},
            "t3.medium":  {"vcpu": 2, "memory_gb": 4,    "architecture": "amd64"},
            "t3.large":   {"vcpu": 2, "memory_gb": 8,    "architecture": "amd64"},
            "t3.xlarge":  {"vcpu": 4, "memory_gb": 16,   "architecture": "amd64"},
            "t3.2xlarge": {"vcpu": 8, "memory_gb": 32,   "architecture": "amd64"},
            "t3a.nano":    {"vcpu": 2, "memory_gb": 0.5, "architecture": "amd64"},
            "t3a.micro":   {"vcpu": 2, "memory_gb": 1,   "architecture": "amd64"},
            "t3a.small":   {"vcpu": 2, "memory_gb": 2,   "architecture": "amd64"},
            "t3a.medium":  {"vcpu": 2, "memory_gb": 4,   "architecture": "amd64"},
            "t3a.large":   {"vcpu": 2, "memory_gb": 8,   "architecture": "amd64"},
            "t3a.xlarge":  {"vcpu": 4, "memory_gb": 16,  "architecture": "amd64"},
            "t3a.2xlarge": {"vcpu": 8, "memory_gb": 32,  "architecture": "amd64"},
            "t4g.nano":    {"vcpu": 2, "memory_gb": 0.5, "architecture": "arm64"},
            "t4g.micro":   {"vcpu": 2, "memory_gb": 1,   "architecture": "arm64"},
            "t4g.small":   {"vcpu": 2, "memory_gb": 2,   "architecture": "arm64"},
            "t4g.medium":  {"vcpu": 2, "memory_gb": 4,   "architecture": "arm64"},
            "t4g.large":   {"vcpu": 2, "memory_gb": 8,   "architecture": "arm64"},
            "t4g.xlarge":  {"vcpu": 4, "memory_gb": 16,  "architecture": "arm64"},
            "t4g.2xlarge": {"vcpu": 8, "memory_gb": 32,  "architecture": "arm64"},
            "m5.large":   {"vcpu": 2,  "memory_gb": 8,   "architecture": "amd64"},
            "m5.xlarge":  {"vcpu": 4,  "memory_gb": 16,  "architecture": "amd64"},
            "m5.2xlarge": {"vcpu": 8,  "memory_gb": 32,  "architecture": "amd64"},
            "m5.4xlarge": {"vcpu": 16, "memory_gb": 64,  "architecture": "amd64"},
            "m5.8xlarge": {"vcpu": 32, "memory_gb": 128, "architecture": "amd64"},
            "m6i.large":   {"vcpu": 2,  "memory_gb": 8,   "architecture": "amd64"},
            "m6i.xlarge":  {"vcpu": 4,  "memory_gb": 16,  "architecture": "amd64"},
            "m6i.2xlarge": {"vcpu": 8,  "memory_gb": 32,  "architecture": "amd64"},
            "m6i.4xlarge": {"vcpu": 16, "memory_gb": 64,  "architecture": "amd64"},
            "m6a.large":   {"vcpu": 2,  "memory_gb": 8,   "architecture": "amd64"},
            "m6a.xlarge":  {"vcpu": 4,  "memory_gb": 16,  "architecture": "amd64"},
            "m6a.2xlarge": {"vcpu": 8,  "memory_gb": 32,  "architecture": "amd64"},
            "m6g.medium":  {"vcpu": 1,  "memory_gb": 4,   "architecture": "arm64"},
            "m6g.large":   {"vcpu": 2,  "memory_gb": 8,   "architecture": "arm64"},
            "m6g.xlarge":  {"vcpu": 4,  "memory_gb": 16,  "architecture": "arm64"},
            "m6g.2xlarge": {"vcpu": 8,  "memory_gb": 32,  "architecture": "arm64"},
            "m6g.4xlarge": {"vcpu": 16, "memory_gb": 64,  "architecture": "arm64"},
            "c5.large":   {"vcpu": 2,  "memory_gb": 4,   "architecture": "amd64"},
            "c5.xlarge":  {"vcpu": 4,  "memory_gb": 8,   "architecture": "amd64"},
            "c5.2xlarge": {"vcpu": 8,  "memory_gb": 16,  "architecture": "amd64"},
            "c5.4xlarge": {"vcpu": 16, "memory_gb": 32,  "architecture": "amd64"},
            "c6i.large":   {"vcpu": 2,  "memory_gb": 4,   "architecture": "amd64"},
            "c6i.xlarge":  {"vcpu": 4,  "memory_gb": 8,   "architecture": "amd64"},
            "c6i.2xlarge": {"vcpu": 8,  "memory_gb": 16,  "architecture": "amd64"},
            "c6i.4xlarge": {"vcpu": 16, "memory_gb": 32,  "architecture": "amd64"},
            "c6a.large":   {"vcpu": 2,  "memory_gb": 4,   "architecture": "amd64"},
            "c6a.xlarge":  {"vcpu": 4,  "memory_gb": 8,   "architecture": "amd64"},
            "c6a.2xlarge": {"vcpu": 8,  "memory_gb": 16,  "architecture": "amd64"},
            "c6g.medium":  {"vcpu": 1,  "memory_gb": 2,   "architecture": "arm64"},
            "c6g.large":   {"vcpu": 2,  "memory_gb": 4,   "architecture": "arm64"},
            "c6g.xlarge":  {"vcpu": 4,  "memory_gb": 8,   "architecture": "arm64"},
            "c6g.2xlarge": {"vcpu": 8,  "memory_gb": 16,  "architecture": "arm64"},
            "c6g.4xlarge": {"vcpu": 16, "memory_gb": 32,  "architecture": "arm64"},
            "r5.large":   {"vcpu": 2,  "memory_gb": 16,  "architecture": "amd64"},
            "r5.xlarge":  {"vcpu": 4,  "memory_gb": 32,  "architecture": "amd64"},
            "r5.2xlarge": {"vcpu": 8,  "memory_gb": 64,  "architecture": "amd64"},
            "r5.4xlarge": {"vcpu": 16, "memory_gb": 128, "architecture": "amd64"},
            "r6i.large":   {"vcpu": 2,  "memory_gb": 16,  "architecture": "amd64"},
            "r6i.xlarge":  {"vcpu": 4,  "memory_gb": 32,  "architecture": "amd64"},
            "r6i.2xlarge": {"vcpu": 8,  "memory_gb": 64,  "architecture": "amd64"},
            "r6g.medium":  {"vcpu": 1,  "memory_gb": 8,   "architecture": "arm64"},
            "r6g.large":   {"vcpu": 2,  "memory_gb": 16,  "architecture": "arm64"},
            "r6g.xlarge":  {"vcpu": 4,  "memory_gb": 32,  "architecture": "arm64"},
            "r6g.2xlarge": {"vcpu": 8,  "memory_gb": 64,  "architecture": "arm64"},
        }

    def rank_pools(
        self,
        node_template: NodeTemplate,
        region: str = "ap-south-1",
        limit: int = 10,
        node_id: Optional[str] = None,
    ) -> List[ScoredPool]:
        """
        Two-tier pool selection pipeline.

        Tier 1 (global, Redis-cached, 65 min TTL):
            Run full ML pipeline on ALL catalog instances with no template filter.
            Cache top GLOBAL_CACHE_LIMIT pools per region sorted by ML score.

        Tier 2 (per-request, in-memory, fast):
            Apply node template + client-specific filters to the cached pools.
            Return top `limit` matching pools.

        When a pool is blacklisted via update_global_cache_on_blacklist(),
        n=n replacement finds new pools without a full recompute.

        Args:
            node_template: User-defined filtering requirements
            region: AWS region
            limit: Maximum number of pools to return
            node_id: Optional EC2 instance ID of the source node. When provided,
                     pod request profile (node_resource_profile:{node_id}) is used
                     to lower the vCPU/memory floor, enabling smaller replacements.

        Returns:
            List of scored and ranked instance pools
        """
        logger.debug(f"Starting two-tier pool ranking for region={region}, limit={limit}")

        # ── Tier 1: Get/compute global top-N (cached in Redis) ────────────────
        global_pools = self._get_or_compute_global_rankings(region, GLOBAL_CACHE_LIMIT)

        if not global_pools:
            logger.warning(f"Global pipeline returned no pools for region {region}")
            return []

        # ── Tier 2: Apply client template + per-client blacklist filter ────────
        filtered_pools = self._apply_client_filters(global_pools, node_template, region, limit, node_id=node_id)

        if not filtered_pools:
            logger.warning("No pools matched client template filters — global cache may need expansion")
            return []

        # ── Step 9: Post-score capacity check on client-filtered results ───────
        ranked_pools = self._step9_post_score_capacity_check(filtered_pools, region)
        logger.debug(f"Two-tier pipeline complete: returning {len(ranked_pools)} pools")

        # Cache final results (legacy key for backward compat)
        self._cache_rankings(ranked_pools)

        return ranked_pools

    # =========================================================================
    # TWO-TIER GLOBAL CACHE HELPERS
    # =========================================================================

    def _pool_to_dict(self, pool: "ScoredPool") -> dict:
        """Serialize ScoredPool to a plain dict for Redis JSON storage."""
        return {
            "instance_type": pool.pool.instance_type,
            "az": pool.pool.az,
            "architecture": pool.pool.architecture,
            "vcpu": pool.pool.vcpu,
            "memory_gb": pool.pool.memory_gb,
            "spot_price": pool.pool.spot_price,
            "ondemand_price": pool.pool.ondemand_price,
            "spot_advisor_rank": pool.pool.spot_advisor_rank,
            "has_capacity": pool.pool.has_capacity,
            "capacity_uncertain": pool.pool.capacity_uncertain,
            "predicted_savings": pool.predicted_savings,
            "risk_probability": pool.risk_probability,
            "ml_score": pool.ml_score,
            "is_flagged": pool.is_flagged,
            "rank": pool.rank,
            "timestamp": pool.timestamp.isoformat(),
            "capacity_status": pool.capacity_status,
            "capacity_validated_at": pool.capacity_validated_at,
        }

    def _pool_from_dict(self, d: dict) -> "ScoredPool":
        """Deserialize a ScoredPool from a Redis JSON dict."""
        inner_pool = InstancePool(
            instance_type=d["instance_type"],
            az=d["az"],
            architecture=d["architecture"],
            vcpu=d["vcpu"],
            memory_gb=d["memory_gb"],
            spot_price=d["spot_price"],
            ondemand_price=d["ondemand_price"],
            spot_advisor_rank=d["spot_advisor_rank"],
            has_capacity=d.get("has_capacity", True),
            capacity_uncertain=d.get("capacity_uncertain", False),
        )
        return ScoredPool(
            pool=inner_pool,
            predicted_savings=d["predicted_savings"],
            risk_probability=d["risk_probability"],
            ml_score=d["ml_score"],
            is_flagged=d["is_flagged"],
            rank=d["rank"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            capacity_status=d.get("capacity_status"),
            capacity_validated_at=d.get("capacity_validated_at"),
        )

    def _build_all_candidate_pools(self, region: str) -> List[InstancePool]:
        """
        Build candidate pools from ALL catalog entries × region AZs.
        No node-template filtering — used for the global cache pipeline.
        """
        azs = self._get_region_azs(region)
        candidate_pools = []
        for instance_type, specs in self.instance_catalog.items():
            for az in azs:
                candidate_pools.append(InstancePool(
                    instance_type=instance_type,
                    az=az,
                    architecture=specs["architecture"],
                    vcpu=specs["vcpu"],
                    memory_gb=specs["memory_gb"],
                    spot_price=0.0,
                    ondemand_price=0.0,
                    spot_advisor_rank=0,
                ))
        return candidate_pools

    def _run_global_pipeline(
        self, region: str, global_limit: int = GLOBAL_CACHE_LIMIT
    ) -> List["ScoredPool"]:
        """
        Run the full ML pipeline on ALL catalog instances (no template filter).
        Returns top `global_limit` pools sorted by ML score.
        Called by _get_or_compute_global_rankings on a cache miss.

        Tiered Spot Advisor filtering (5 passes, stops when global_limit met):
          Pass 0: max_rank=0 (<5% interruption only — safest pools)
          Pass 1: max_rank=1 (≤10% interruption — <5% and 5-10%)
          Pass 2: max_rank=2 (≤15% interruption — includes 10-15% overflow)
          Pass 3: max_rank=3 (≤20% interruption — needed for COST_FIRST profiles)
          Pass 4: max_rank=4 (≤25% interruption — maximum ceiling, all profiles)
        Note: Global cache must retain ALL pools up to rank 4 so per-cluster
        COST_FIRST filters (which accept up to 25%) can find their candidates.
        Filtering at global tier before per-cluster filter = silent pool loss.
        """
        logger.info(f"Global pipeline START for region={region} (no template filter)")

        # Ensure Spot Advisor data is available for this region
        self._ensure_spot_advisor_fresh(region)

        all_candidate_pools = self._build_all_candidate_pools(region)
        logger.info(f"Global pipeline: {len(all_candidate_pools)} raw candidates")

        # ── Tiered Spot Advisor filter (3 passes) ─────────────────────────

        # Pass 0: Strictest — only <5% interruption (rank 0)
        candidate_pools = self._step3_spot_advisor_filter(
            all_candidate_pools, region, max_rank=0
        )
        logger.info(
            f"Global Step 3 (pass 0, <5%%): {len(candidate_pools)} after "
            f"Spot Advisor filter"
        )

        scored_pools = self._score_candidates(candidate_pools, region)
        logger.info(
            f"Global Step 3 (pass 0): {len(scored_pools)} scored pools"
        )

        # Pass 1: If not enough, expand to ≤10% interruption (ranks 0-1)
        if len(scored_pools) < global_limit:
            pass0_keys = {
                f"{p.pool.instance_type}:{p.pool.az}" for p in scored_pools
            }
            expanded_pools = self._step3_spot_advisor_filter(
                all_candidate_pools, region, max_rank=1
            )
            overflow_pools = [
                p for p in expanded_pools
                if f"{p.instance_type}:{p.az}" not in pass0_keys
            ]
            logger.info(
                f"Global Step 3 (pass 1, ≤10%%): {len(overflow_pools)} "
                f"additional 5-10%% pools added"
            )

            if overflow_pools:
                overflow_scored = self._score_candidates(
                    overflow_pools, region
                )
                scored_pools.extend(overflow_scored)

        # Pass 2: If still not enough, expand to ≤15% interruption (rank 2)
        if len(scored_pools) < global_limit:
            pass01_keys = {
                f"{p.pool.instance_type}:{p.pool.az}" for p in scored_pools
            }
            expanded_pools = self._step3_spot_advisor_filter(
                all_candidate_pools, region, max_rank=2
            )
            # Keep only the newly-included rank-2 pools
            overflow_pools = [
                p for p in expanded_pools
                if f"{p.instance_type}:{p.az}" not in pass01_keys
            ]
            logger.info(
                f"Global Step 3 (pass 2, ≤15%%): {len(overflow_pools)} "
                f"additional 10-15%% pools added"
            )

            if overflow_pools:
                overflow_scored = self._score_candidates(
                    overflow_pools, region
                )
                scored_pools.extend(overflow_scored)

        # Pass 3: If still not enough, expand to ≤20% interruption (rank 3)
        # Required for COST_FIRST profiles which accept up to 25% interruption.
        # Without this pass, COST_FIRST never sees 15-20% pools (silent loss).
        if len(scored_pools) < global_limit:
            pass012_keys = {
                f"{p.pool.instance_type}:{p.pool.az}" for p in scored_pools
            }
            expanded_pools = self._step3_spot_advisor_filter(
                all_candidate_pools, region, max_rank=3
            )
            overflow_pools = [
                p for p in expanded_pools
                if f"{p.instance_type}:{p.az}" not in pass012_keys
            ]
            logger.info(
                f"Global Step 3 (pass 3, ≤20%%): {len(overflow_pools)} "
                f"additional 15-20%% pools added"
            )

            if overflow_pools:
                overflow_scored = self._score_candidates(
                    overflow_pools, region
                )
                scored_pools.extend(overflow_scored)

        # Pass 4: If still not enough, expand to ≤25% interruption (rank 4)
        # Maximum ceiling — covers all possible profile ceilings (COST_FIRST: 25%).
        if len(scored_pools) < global_limit:
            pass0123_keys = {
                f"{p.pool.instance_type}:{p.pool.az}" for p in scored_pools
            }
            expanded_pools = self._step3_spot_advisor_filter(
                all_candidate_pools, region, max_rank=4
            )
            overflow_pools = [
                p for p in expanded_pools
                if f"{p.instance_type}:{p.az}" not in pass0123_keys
            ]
            logger.info(
                f"Global Step 3 (pass 4, ≤25%%): {len(overflow_pools)} "
                f"additional 20-25%% pools added"
            )

            if overflow_pools:
                overflow_scored = self._score_candidates(
                    overflow_pools, region
                )
                scored_pools.extend(overflow_scored)

        if not scored_pools:
            return []

        # Sort descending by ML score; dedup by instance type
        scored_pools.sort(
            key=lambda p: (p.ml_score, p.predicted_savings, -p.pool.spot_price),
            reverse=True,
        )
        seen_types: set = set()
        diverse: List["ScoredPool"] = []
        for pool in scored_pools:
            if pool.pool.instance_type not in seen_types:
                diverse.append(pool)
                seen_types.add(pool.pool.instance_type)

        result = diverse[:global_limit]
        for i, pool in enumerate(result, start=1):
            pool.rank = i

        logger.info(f"Global pipeline DONE: {len(result)} pools cached for region={region}")
        return result

    def _score_candidates(
        self, candidate_pools: List[InstancePool], region: str
    ) -> List["ScoredPool"]:
        """
        Run steps 4→7 on a list of candidate pools and return scored pools
        that pass the risk cutoff.
        """
        if not candidate_pools:
            return []

        # Step 4: Hard-reject repeat blacklist offenders (failure_count >= 3)
        candidate_pools = self._step4_blacklist_check(candidate_pools, region)

        # Step 6: Fetch spot + on-demand prices
        candidate_pools = self._step6_price_fetch(candidate_pools, region)

        # Step 7: ML scoring
        scored_pools = self._step7_ml_scoring(candidate_pools, region)

        # Safety net: if ONNX risk gate is over-aggressive (<10 pools survive), or
        # all were rejected, fall back to heuristic scoring.
        # Threshold of 10: fewer than 10 ONNX-approved pools from 800+ candidates
        # indicates the model is miscalibrated for this region/pool mix.
        if len(scored_pools) < 10 and candidate_pools:
            logger.warning(
                f"[pool_ranking] _step7_ml_scoring returned only {len(scored_pools)} pools "
                f"for {len(candidate_pools)} candidates in {region} — activating fallback scoring"
            )
            scored_pools = self._fallback_scoring(candidate_pools)

        # Intelligence risk cutoff (fallback gives risk=0.20, always passes 0.50 gate)
        scored_pools = [p for p in scored_pools if p.risk_probability <= 0.50]

        return scored_pools

    def _get_or_compute_global_rankings(
        self, region: str, global_limit: int = GLOBAL_CACHE_LIMIT
    ) -> List["ScoredPool"]:
        """
        Tier 1: Return global top-N pools from Redis cache; compute if missing.

        Cache key : global_pool_rankings:{region}
        TTL       : GLOBAL_CACHE_TTL (65 minutes)
        """
        cache_key = f"global_pool_rankings:{region}"

        # Cache hit
        try:
            cached = self.redis.get(cache_key)
            if cached:
                pool_dicts = json.loads(cached)
                if not isinstance(pool_dicts, list):
                    logger.warning(f"Global cache corrupt for {region}: expected list, got {type(pool_dicts).__name__}")
                    self.redis.delete(cache_key)
                else:
                    pools = [self._pool_from_dict(d) for d in pool_dicts]
                    logger.debug(f"Global cache HIT for {region}: {len(pools)} pools")
                    return pools
        except Exception as e:
            logger.warning(f"Global cache read failed for {region}: {e}")

        # Cache miss — run full global pipeline
        # Acquire a short-lived Redis lock so concurrent requests don't all pile
        # into the pipeline simultaneously (OOM pressure, duplicate work).
        _pipeline_lock_key = f"global_pipeline_running:{region}"
        _lock_acquired = False
        _lock_value = str(uuid.uuid4())  # Fencing token — only owner may release
        try:
            _lock_acquired = bool(self.redis.set(_pipeline_lock_key, _lock_value, nx=True, ex=120))
            if not _lock_acquired:
                # Another worker is building the cache — wait briefly and re-check
                import time as _t
                for _ in range(6):
                    _t.sleep(5)
                    _retry = self.redis.get(cache_key)
                    if _retry:
                        pool_dicts = json.loads(_retry)
                        pools = [self._pool_from_dict(d) for d in pool_dicts]
                        logger.debug(f"Global cache HIT (waited for pipeline) for {region}: {len(pools)} pools")
                        return pools
                logger.warning(f"Global pipeline lock wait timed out for {region}, running pipeline anyway")
        except Exception:
            pass  # Redis unavailable — proceed without lock

        logger.info(f"Global cache MISS for {region} — running full pipeline")
        try:
            global_pools = self._run_global_pipeline(region, global_limit)
        finally:
            # Only release the lock if we still own it (fenced: compare stored value)
            if _lock_acquired:
                try:
                    _current = self.redis.get(_pipeline_lock_key)
                    if _current == _lock_value:
                        self.redis.delete(_pipeline_lock_key)
                except Exception:
                    pass

        # Only cache non-empty results — caching [] would cause subsequent calls to
        # read an empty "hit" instead of retrying the full pipeline on next request.
        if global_pools:
            try:
                cache_data = [self._pool_to_dict(p) for p in global_pools]
                self.redis.setex(cache_key, GLOBAL_CACHE_TTL, json.dumps(cache_data))
                logger.info(
                    f"Global cache STORED for {region}: {len(global_pools)} pools "
                    f"(TTL={GLOBAL_CACHE_TTL}s)"
                )
            except Exception as e:
                logger.error(f"Global cache write failed for {region}: {e}")
        else:
            logger.warning(
                f"Global pipeline returned 0 pools for {region} — skipping cache write "
                f"so next request retries the full pipeline"
            )

        return global_pools

    def _apply_client_filters(
        self,
        global_pools: List["ScoredPool"],
        template: NodeTemplate,
        region: str,
        limit: int,
        node_id: Optional[str] = None,
    ) -> List["ScoredPool"]:
        """
        Tier 2: Apply node-template + per-client blacklist filters to the cached
        global pool list.  Runs entirely in-memory — no DB or AWS calls.

        Filters applied (in order):
          • Architecture
          • vCPU range  (can be tightened from pod requests via node_resource_profile:{node_id})
          • Memory range (same)
          • Allowed families (template.allowed_families)
          • Allowed sizes   (template.allowed_sizes)
          • Allowed AZs     (template.allowed_azs)
          • Excluded instance types
          • Hard blacklist: failure_count >= 3 (client-side defense)

        Re-ranks filtered pools 1 → N.
        """
        blacklist_failures_prefix = "blacklist_failures:"
        filtered: List["ScoredPool"] = []

        # ── Fix 11: Pod-request-based capacity floor ─────────────────────────
        # If a node_resource_profile exists for node_id, use actual pod requests
        # (+ 10% headroom) as the minimum vCPU/memory floor instead of node total.
        # This allows smaller, cheaper replacements when the node is underutilized.
        effective_vcpu_min = template.vcpu_range[0]
        effective_mem_min = template.memory_range[0]
        if node_id:
            try:
                raw_profile = self.redis.get(f"node_resource_profile:{node_id}")
                if raw_profile:
                    import json as _json
                    profile = _json.loads(raw_profile)
                    vcpu_req = profile.get("vcpu_requested")
                    mem_req = profile.get("memory_gb_requested")
                    headroom = profile.get("replacement_headroom_pct", 10)
                    if vcpu_req and vcpu_req > 0:
                        effective_vcpu_min = max(1, int(vcpu_req * (1 + headroom / 100) + 0.999))
                    if mem_req and mem_req > 0:
                        import math
                        effective_mem_min = math.ceil(mem_req * (1 + headroom / 100))
            except Exception:
                pass  # fallback to template values on any error

        # Normalize architecture names: treat x86_64 and amd64 as equivalent
        # (frontend sends "x86_64", catalog stores "amd64")
        _ARCH_ALIASES = {"x86_64": "amd64", "amd64": "x86_64"}
        normalized_archs = set(template.architecture)
        for arch in list(template.architecture):
            if arch in _ARCH_ALIASES:
                normalized_archs.add(_ARCH_ALIASES[arch])

        for pool in global_pools:
            p = pool.pool

            # Architecture (normalized: x86_64 == amd64)
            if p.architecture not in normalized_archs:
                continue

            # vCPU range (lower bound from pod requests if available, upper from template)
            if not (effective_vcpu_min <= p.vcpu <= template.vcpu_range[1]):
                continue

            # Memory range (lower bound from pod requests if available, upper from template)
            if not (effective_mem_min <= p.memory_gb <= template.memory_range[1]):
                continue

            # Allowed families
            family = p.instance_type.split(".")[0]
            if template.allowed_families and family not in template.allowed_families:
                continue

            # Allowed sizes
            size = p.instance_type.split(".")[1]
            if template.allowed_sizes and size not in template.allowed_sizes:
                continue

            # Allowed AZs
            if template.allowed_azs and p.az not in template.allowed_azs:
                continue

            # Excluded instance types
            if (
                template.excluded_instance_types
                and p.instance_type in template.excluded_instance_types
            ):
                continue

            # Hard blacklist re-check (client-specific defense)
            pool_key = f"{p.instance_type}:{p.az}"
            try:
                failure_count = int(
                    self.redis.get(f"{blacklist_failures_prefix}{pool_key}") or 0
                )
                if failure_count >= 3:
                    continue
            except Exception:
                pass

            # Price gate: only include pools where spot is cheaper than the source OD price.
            # Without this, a pool whose spot price >= source OD provides negative savings.
            if template.source_od_price and template.source_od_price > 0:
                if p.spot_price >= template.source_od_price:
                    continue

            filtered.append(pool)
            if len(filtered) >= limit:
                break

        # Re-rank 1 → N relative to client view
        for i, pool in enumerate(filtered, start=1):
            pool.rank = i

        logger.debug(
            f"Client filter: {len(global_pools)} global → {len(filtered)} matching "
            f"(limit={limit})"
        )
        return filtered

    def update_global_cache_on_blacklist(
        self, instance_type: str, az: str, region: str
    ) -> None:
        """
        n=n blacklist replacement: remove the newly blacklisted pool from the
        global Redis cache and add an equal number of next-best replacement pools.

        Called by BlacklistService after a pool is blacklisted.
        Does NOT trigger a full global recompute — only scores uncached candidates.
        """
        cache_key = f"global_pool_rankings:{region}"

        try:
            cached = self.redis.get(cache_key)
            if not cached:
                logger.info(
                    f"No global cache for {region} — blacklist update will apply "
                    "on next compute"
                )
                return

            pool_dicts: List[dict] = json.loads(cached)
            pool_key = f"{instance_type}:{az}"

            # Remove the blacklisted pool(s)
            before_count = len(pool_dicts)
            pool_dicts = [
                d for d in pool_dicts
                if f"{d['instance_type']}:{d['az']}" != pool_key
            ]
            removed = before_count - len(pool_dicts)

            if removed == 0:
                logger.info(
                    f"Pool {pool_key} not found in global cache for {region} — no update needed"
                )
                return

            logger.info(
                f"Removed {removed} blacklisted pool(s) from global cache "
                f"({region}): {pool_key}"
            )

            # Find n replacement pools not already in cache
            cached_keys = {f"{d['instance_type']}:{d['az']}" for d in pool_dicts}
            replacements = self._find_replacement_pools(region, cached_keys, n=removed)

            if replacements:
                pool_dicts.extend([self._pool_to_dict(r) for r in replacements])
                # Re-sort descending by ml_score and re-rank
                pool_dicts.sort(key=lambda d: d["ml_score"], reverse=True)
                for i, d in enumerate(pool_dicts, start=1):
                    d["rank"] = i
                logger.info(
                    f"Added {len(replacements)} replacement pool(s) to global cache "
                    f"({region})"
                )

            # Write updated cache, preserving remaining TTL where possible
            remaining_ttl = self.redis.ttl(cache_key)
            ttl = remaining_ttl if remaining_ttl and remaining_ttl > 0 else GLOBAL_CACHE_TTL
            self.redis.setex(cache_key, ttl, json.dumps(pool_dicts))

        except Exception as e:
            logger.error(
                f"Failed to update global cache on blacklist for {region}: {e}"
            )

    def _find_replacement_pools(
        self, region: str, exclude_keys: set, n: int = 1
    ) -> List["ScoredPool"]:
        """
        Score uncached candidate pools to find n next-best replacements.
        Only runs the pipeline on instance×AZ combos NOT already in the cache.
        """
        azs = self._get_region_azs(region)
        uncached: List[InstancePool] = []

        for instance_type, specs in self.instance_catalog.items():
            for az in azs:
                if f"{instance_type}:{az}" not in exclude_keys:
                    uncached.append(InstancePool(
                        instance_type=instance_type,
                        az=az,
                        architecture=specs["architecture"],
                        vcpu=specs["vcpu"],
                        memory_gb=specs["memory_gb"],
                        spot_price=0.0,
                        ondemand_price=0.0,
                        spot_advisor_rank=0,
                    ))

        if not uncached:
            return []

        uncached = self._step3_spot_advisor_filter(uncached, region)
        uncached = self._step4_blacklist_check(uncached, region)
        uncached = self._step6_price_fetch(uncached, region)
        scored = self._step7_ml_scoring(uncached, region)
        scored = [p for p in scored if p.risk_probability <= 0.50]

        if not scored:
            return []

        scored.sort(key=lambda p: p.ml_score, reverse=True)
        logger.info(
            f"Replacement search: {len(uncached)} uncached candidates → "
            f"{len(scored)} scored → returning top {n}"
        )
        return scored[:n]

    def _step1_node_template_filter(
        self,
        template: NodeTemplate,
        region: str
    ) -> List[InstancePool]:
        """
        Step 1: Filter instance types based on user-defined requirements.

        Filters by: architecture, vCPU range, memory range, allowed families/sizes.
        """
        candidate_pools = []

        for instance_type, specs in self.instance_catalog.items():
            # Check architecture
            if specs["architecture"] not in template.architecture:
                continue

            # Check vCPU range
            if not (template.vcpu_range[0] <= specs["vcpu"] <= template.vcpu_range[1]):
                continue

            # Check memory range
            if not (template.memory_range[0] <= specs["memory_gb"] <= template.memory_range[1]):
                continue

            # Check family filter
            family = instance_type.split('.')[0]
            if template.allowed_families and family not in template.allowed_families:
                continue

            # Check size filter
            size = instance_type.split('.')[1]
            if template.allowed_sizes and size not in template.allowed_sizes:
                continue

            # Check exclusion list
            if template.excluded_instance_types and instance_type in template.excluded_instance_types:
                continue

            # Generate pool for each AZ in region
            azs = self._get_region_azs(region)
            for az in azs:
                candidate_pools.append(InstancePool(
                    instance_type=instance_type,
                    az=az,
                    architecture=specs["architecture"],
                    vcpu=specs["vcpu"],
                    memory_gb=specs["memory_gb"],
                    spot_price=0.0,  # Will be fetched in Step 6
                    ondemand_price=0.0,  # Will be fetched in Step 6
                    spot_advisor_rank=0  # Will be fetched in Step 3
                ))

        return candidate_pools

    def _step2_az_filter(
        self,
        pools: List[InstancePool],
        allowed_azs: Optional[List[str]]
    ) -> List[InstancePool]:
        """Step 2: Filter pools by user-specified AZs."""
        if not allowed_azs:
            return pools  # No AZ filter specified

        return [pool for pool in pools if pool.az in allowed_azs]

    def _step3_spot_advisor_filter(
        self,
        pools: List[InstancePool],
        region: str = "ap-south-1",
        max_rank: int = 1,
    ) -> List[InstancePool]:
        """
        Step 3: Filter pools using AWS Spot Advisor frequency rank.

        Interruption index mapping (from AWS Spot Advisor):
          0 = <5%    (safest)
          1 = 5-10%
          2 = 10-15%
          3 = 15-20%
          4 = >20%   (riskiest)

        Args:
            max_rank: Maximum allowed interruption index.
                      Default 1 (≤10%).  Called with 2/3/4 for overflow passes.
                      Unknown instance types receive rank=4 (worst-case) so they
                      only survive pass 4, never appearing as falsely-safe.
        """
        spot_advisor_data = self._get_spot_advisor_data()

        filtered_pools = []
        fallback_count = 0
        for pool in pools:
            # Check AZ-specific first, then fall back to Region-wide rank,
            # default 1 (5-10%) — conservative assumption when no data exists
            rank = spot_advisor_data.get(f"{pool.instance_type}:{pool.az}")
            if rank is None:
                rank = spot_advisor_data.get(f"{pool.instance_type}:{region}")
                if rank is None:
                    rank = 4  # Worst-case fallback — unknown families rank last, not safe
                    fallback_count += 1

            pool.spot_advisor_rank = rank

            if rank <= max_rank:
                filtered_pools.append(pool)

        if fallback_count > 0:
            logger.warning(
                f"[SPOT-ADVISOR] {fallback_count}/{len(pools)} pools used "
                f"fallback rank=4 (worst-case — no Spot Advisor data found). "
                f"These pools will only appear in pass 4 (≤25%% ceiling). "
                f"Ensure the Spot Advisor scraper has run for region={region}."
            )

        return filtered_pools

    def _step4_blacklist_check(self, pools: List[InstancePool], region: str = "ap-south-1") -> List[InstancePool]:
        """
        Step 4: Check global blacklist (risky pools flagged by System B).

        - Repeat offenders (failure_count >= 3): HARD REJECT (removed from pipeline)
        - First/second offenders (failure_count 1-2): Kept but flagged for penalty in Step 7
        - Non-blacklisted pools: Pass through unchanged

        TTL: 24 hours base, exponential backoff for repeat offenders.
        """
        blacklist_set_key = f"risky_pools:{region}"
        passed = []
        rejected = 0

        for pool in pools:
            pool_key = f"{pool.instance_type}:{pool.az}"

            # Check if pool is in blacklist set
            is_flagged = self.redis.sismember(blacklist_set_key, pool_key)

            if not is_flagged:
                # Also check legacy/global key for backward compat
                is_flagged = self.redis.sismember("risky_pools", pool_key)

            if is_flagged:
                # Check failure count to decide hard-reject vs soft-flag
                failure_count = int(self.redis.get(f"blacklist_failures:{pool_key}") or 0)  # P-M22 fix: consistent default 0

                if failure_count >= 3:
                    # Hard reject repeat offenders
                    rejected += 1
                    logger.debug(
                        f"BLACKLIST REJECTED {pool_key}: "
                        f"failure_count={failure_count} (>= 3 threshold)"
                    )
                    continue
                else:
                    # Keep but flag for penalty in Step 7
                    logger.debug(
                        f"BLACKLIST FLAGGED {pool_key}: "
                        f"failure_count={failure_count} (will be penalized in ML scoring)"
                    )

            passed.append(pool)

        if rejected > 0:
            logger.info(f"Step 4: Blacklist rejected {rejected} repeat-offender pools")

        return passed

    def _step5_capacity_check(
        self,
        pools: List[InstancePool],
        region: str
    ) -> List[InstancePool]:
        """
        Step 5: Validate real-time capacity using AWS API.

        Uses ThreadPoolExecutor for parallel capacity validation.
        Pools that time out are included but flagged as capacity_uncertain.
        """
        def _check_single_capacity(pool: InstancePool, region: str) -> bool:
            """
            Check capacity for a single pool via RunInstances --dry-run.
            Results are cached in Redis for 15 minutes.
            """
            cache_key = f"capacity:{pool.instance_type}:{pool.az}"
            cached = self.redis.get(cache_key)
            if cached is not None:
                return cached == b"1" or cached == "1"

            # Real AWS capacity check using RunInstances --dry-run
            has_capacity = self._check_aws_capacity(pool.instance_type, pool.az, region)

            # Cache result for 15 minutes
            self.redis.setex(cache_key, 900, "1" if has_capacity else "0")
            return has_capacity

        # Parallel capacity check with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_check_single_capacity, pool, region): pool 
                for pool in pools
            }
            for future in as_completed(futures, timeout=30):
                pool = futures[future]
                try:
                    pool.has_capacity = future.result()
                except TimeoutError:
                    pool.has_capacity = True  # Assume capacity on timeout, don't block ranking
                    pool.capacity_uncertain = True
                    logger.warning(f"Capacity check timed out for {pool.instance_type}/{pool.az}")
                except Exception as e:
                    pool.has_capacity = True  # Assume capacity on error
                    pool.capacity_uncertain = True
                    logger.warning(f"Capacity check failed for {pool.instance_type}/{pool.az}: {e}")

        return [pool for pool in pools if pool.has_capacity]

    def _step6_price_fetch(
        self,
        pools: List[InstancePool],
        region: str
    ) -> List[InstancePool]:
        """
        Step 6: Fetch current spot and on-demand prices from AWS Pricing API.
        """
        pricing_data = self._get_pricing_data(region)

        for pool in pools:
            pricing_key = f"{pool.instance_type}:{pool.az}"
            prices = pricing_data.get(pricing_key, {})

            # Get prices with realistic defaults (spot is ~30% of on-demand)
            spot_price = prices.get('spot', None)
            ondemand_price = prices.get('ondemand', None)

            # If both missing, use instance-type-based estimates
            if spot_price is None or ondemand_price is None:
                # Estimate based on instance size/family
                base_price = self._estimate_instance_price(pool.instance_type)
                pool.spot_price = spot_price if spot_price is not None else base_price * 0.30
                pool.ondemand_price = ondemand_price if ondemand_price is not None else base_price
            else:
                pool.spot_price = spot_price
                pool.ondemand_price = ondemand_price

            # Safety check: ensure spot is never 0.0 or >= ondemand
            if pool.spot_price <= 0.0:
                pool.spot_price = pool.ondemand_price * 0.30
            if pool.spot_price >= pool.ondemand_price:
                pool.spot_price = pool.ondemand_price * 0.70

        return pools

    def _step7_ml_scoring(self, pools: List[InstancePool], region: str = "ap-south-1") -> List[ScoredPool]:
        """
        Step 7: ML Model Scoring using ONNX models.

        Includes circuit breaker: if ONNX fails >5 times in 10 minutes,
        switches to fallback scoring and sets degraded mode flag.

        For each pool:
        1. Engineer 45 features
        2. Run classifier_6.onnx → risk_probability (volatile zone chance, 0-1)
        3. Run regressor_6.onnx → predicted_savings (savings vs on-demand, 0-1)
        4. Hard filter: REJECT pools where risk_probability > optimal_threshold
        5. Check System B blacklist flags → apply savings penalty if risky
        6. Calculate composite score = (savings × savings_weight) - (risk × risk_weight)
        """
        # ── Circuit Breaker Check ──────────────────────────────────
        ml_fail_count = int(self.redis.get("ascpai:ml_fail_count") or 0)
        if ml_fail_count > 5:
            self.redis.set("ascpai:ml_degraded", "true", ex=600)  # 10-minute flag
            logger.error("ML circuit breaker OPEN — using fallback scoring (>5 failures in 10 min)")
            return self._fallback_scoring(pools)

        if not self.classifier_session or not self.regressor_session:
            logger.error("ONNX models not loaded - using fallback scoring")
            # Increment circuit breaker counter
            pipe = self.redis.pipeline()
            pipe.incr("ascpai:ml_fail_count")
            pipe.expire("ascpai:ml_fail_count", 600)  # 10-minute window
            pipe.execute()
            return self._fallback_scoring(pools)

        # ── Load Spot Advisor savings percentages for savings differentiation ──
        # When ONNX regressor saturates (gives identical output for all pools in a
        # region), use real AWS Spot Advisor savings% which varies per instance type.
        # e.g. t3.micro=79%, m5.large=73%, c5.large=68%, r5.large=81%
        sa_savings_map: Dict[str, float] = {}
        try:
            from backend.models.pricing import SpotAdvisorData
            sa_records = self.db.query(SpotAdvisorData).filter(
                SpotAdvisorData.os_type == 'Linux'
            ).all()
            for r in sa_records:
                sa_savings_map[r.instance_type] = float(r.savings_percentage)
            logger.debug(f"Loaded {len(sa_savings_map)} SA savings% for scoring differentiation")
        except Exception as _e:
            logger.warning(f"Could not load SA savings data for scoring: {_e}")

        scored_pools = []
        rejected_risky = 0
        timestamp = datetime.utcnow()

        # ── Batch-fetch reputation multipliers (Step 15 / Stage 5.3) ──────────
        # Avoid per-pool Redis round-trips in a tight loop.
        _reputation_mults: Dict[str, float] = {}
        try:
            from backend.services.pool_reputation_service import PoolReputationService as _RepSvc
            _rep_svc = _RepSvc(self.db, self.redis)
            _pool_keys = [f"{p.instance_type}:{p.az}" for p in pools]
            _reputation_mults = _rep_svc.bulk_get_multipliers(_pool_keys)
        except Exception as _rep_init_err:
            logger.debug(f"[pool_ranking] Reputation prefetch skipped: {_rep_init_err}")

        for pool in pools:
            try:
                # Engineer 45 features
                features = self.feature_service.engineer_features(
                    instance_type=pool.instance_type,
                    az=pool.az,
                    spot_price=pool.spot_price,
                    ondemand_price=pool.ondemand_price,
                    timestamp=timestamp,
                    use_minimum=False  # Use full features if available
                )

                # Run ONNX inference — CORRECT assignment:
                # classifier_6.onnx → risk_probability (is_unstable probability)
                # regressor_6.onnx → predicted_savings (future savings %)
                risk_probability = float(self.classifier_session.run(
                    None,
                    {"input": features}
                )[0][0][0])

                predicted_savings = float(self.regressor_session.run(
                    None,
                    {"input": features}
                )[0][0][0])

                # Clamp values to valid range
                risk_probability = max(0.0, min(1.0, risk_probability))
                predicted_savings = max(0.0, min(1.0, predicted_savings))

                # ── Use Spot Advisor savings when ONNX regressor over-saturates ─
                # ONNX regressor outputs identical values for all pools in a region
                # when features are similar (estimated prices all use same ratio).
                # AWS Spot Advisor savings% is measured real-world data that varies
                # meaningfully per instance type (e.g. t3.micro=79%, m5.large=73%).
                if predicted_savings >= 0.99:
                    sa_savings = sa_savings_map.get(pool.instance_type)
                    if sa_savings and sa_savings > 0:
                        # Convert percentage (e.g. 79) → fraction (0.79)
                        predicted_savings = max(0.30, min(0.95, sa_savings / 100.0))
                    elif pool.ondemand_price > 0:
                        # Secondary fallback: real price headroom
                        price_headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price
                        predicted_savings = max(0.0, min(0.95, price_headroom))

                # ── Differentiated risk: 4-signal blend (changes.md §6.2) ────
                # Signals: ONNX (0.40), Price pressure (0.35), Spot Advisor (0.25), + optional EMA
                _pool_key_ema = f"{pool.instance_type}:{pool.az}"
                _ema_risk_val, _ema_weight_val = 0.0, 0.0
                try:
                    from backend.services.global_ema_service import get_ema_risk
                    _ema_risk_val, _ema_weight_val = get_ema_risk(self.redis, self.db, _pool_key_ema)
                except Exception:
                    pass

                risk_probability = PoolRankingService.compute_blended_risk(
                    onnx_risk=risk_probability,
                    sa_rank=pool.spot_advisor_rank,
                    spot_price=pool.spot_price,
                    od_price=pool.ondemand_price,
                    ema_risk=_ema_risk_val,
                    ema_weight=_ema_weight_val,
                )

                # ── Hard filter: REJECT pools above risk threshold ──
                if risk_probability > self.risk_threshold:
                    rejected_risky += 1
                    logger.debug(
                        f"REJECTED {pool.instance_type}/{pool.az}: "
                        f"risk={risk_probability:.3f} > threshold={self.risk_threshold}"
                    )
                    continue

                # Check System B blacklist flag — namespaced by region
                blacklist_key = f"risky_pools:{region}"
                is_flagged = self.redis.sismember(
                    blacklist_key,
                    f"{pool.instance_type}:{pool.az}"
                )

                # Apply savings penalty if blacklisted (reduce attractiveness)
                effective_savings = predicted_savings
                if is_flagged:
                    effective_savings = max(0.0, predicted_savings - 0.20)  # -20% savings penalty

                # ── Unified Score (changes.md §6.1) ──
                # Replaces the simple EV scoring with a multi-signal unified score.
                # unified_score = (savings × weight) × (1 - risk) × reputation × capacity
                # ml_score is kept as deprecated alias pointing to unified_score.
                _pool_key_rep = f"{pool.instance_type}:{pool.az}"
                _rep_mult = _reputation_mults.get(_pool_key_rep, 1.00)
                _rep_mult = max(0.1, min(10.0, _rep_mult))  # Clamp to prevent score corruption

                # Capacity multiplier from dry-run cache
                _cap_mult = 1.0
                try:
                    _dr_key = f"dry_run:{pool.instance_type}:{pool.az}"
                    _dr_val = self.redis.get(_dr_key)
                    if _dr_val:
                        _dr_str = _dr_val.decode() if isinstance(_dr_val, bytes) else _dr_val
                        if _dr_str == 'pass':
                            _cap_mult = 1.0
                        elif _dr_str == 'fail':
                            _cap_mult = 0.0
                        else:
                            _cap_mult = 0.9  # stale / unknown
                except Exception:
                    pass

                # Apply blacklist + dryrun hard overrides to blended risk
                _final_risk_adjusted = PoolRankingService.compute_blended_risk(
                    onnx_risk=risk_probability,  # already blended above, but re-apply overrides
                    sa_rank=pool.spot_advisor_rank,
                    spot_price=pool.spot_price,
                    od_price=pool.ondemand_price,
                    ema_risk=_ema_risk_val,
                    ema_weight=_ema_weight_val,
                    is_blacklisted=bool(is_flagged),
                    dryrun_failed=(_cap_mult == 0.0),
                )

                final_score = PoolRankingService.compute_unified_score(
                    savings_pct=effective_savings,
                    final_risk=_final_risk_adjusted,
                    reputation_mult=_rep_mult,
                    capacity_mult=_cap_mult,
                )

                scored_pools.append(ScoredPool(
                    pool=pool,
                    predicted_savings=predicted_savings,
                    risk_probability=risk_probability,
                    ml_score=final_score,
                    is_flagged=bool(is_flagged),
                    rank=0,  # Will be set in Step 8
                    timestamp=timestamp
                ))

            except Exception as e:
                logger.error(f"ML scoring failed for {pool.instance_type}/{pool.az}: {e}")
                # Increment circuit breaker counter on per-pool ML failure
                pipe = self.redis.pipeline()
                pipe.incr("ascpai:ml_fail_count")
                pipe.expire("ascpai:ml_fail_count", 600)
                pipe.execute()
                continue

        # Clear degraded flag on successful pipeline completion
        if scored_pools:
            self.redis.delete("ascpai:ml_degraded")

        logger.info(
            f"Step 7 complete: {len(scored_pools)} safe pools, "
            f"{rejected_risky} rejected (risk > {self.risk_threshold})"
        )
        return scored_pools

    # ── Unified Score (changes.md §6) ────────────────────────────────────

    @staticmethod
    def compute_unified_score(
        savings_pct: float,
        final_risk: float,
        reputation_mult: float = 1.0,
        capacity_mult: float = 1.0,
        savings_weight: float = 0.8,
    ) -> float:
        """
        Unified score = (savings_pct × savings_weight) × (1 - final_risk) × reputation_mult × capacity_mult

        Args:
            savings_pct:      0-1 (customer savings vs OD baseline)
            final_risk:       0-1 (blended risk from compute_blended_risk)
            reputation_mult:  0.5-1.2 from PoolReputationService
            capacity_mult:    1.0 (pass), 0.9 (stale), 0.0 (fail)
            savings_weight:   default 0.8
        """
        return round(
            (savings_pct * savings_weight) * (1.0 - final_risk) * reputation_mult * capacity_mult,
            6,
        )

    @staticmethod
    def compute_blended_risk(
        onnx_risk: float,
        sa_rank: int,
        spot_price: float,
        od_price: float,
        ema_risk: float = 0.0,
        ema_weight: float = 0.0,
        is_blacklisted: bool = False,
        dryrun_failed: bool = False,
    ) -> float:
        """
        3-signal blended risk with EMA smoothing (changes.md §6.2).

        Base signals (when EMA weight = 0):
          ONNX: 0.40, Price pressure: 0.35, Spot Advisor: 0.25

        When EMA data is present, EMA weight is injected (max 40%) and
        base weights are renormalized to (1 - ema_weight).
        EMA is an interpolation modifier, not an independent 4th signal.

        Hard overrides:
          - blacklisted (ITN in last 24h) → max(0.75, risk)
          - dryrun failed               → max(0.65, risk)
        """
        # Price pressure signal
        headroom = (od_price - spot_price) / od_price if od_price > 0 else 0.0
        price_pressure = max(0.0, 1.0 - headroom / 0.40)

        # Spot Advisor signal
        sa_risk = min(sa_rank / 5.0, 0.8)

        # Base weights
        base_onnx = 0.40
        base_price = 0.35
        base_sa = 0.25
        base_sum = base_onnx + base_price + base_sa

        weighted_sum = base_onnx * onnx_risk + base_price * price_pressure + base_sa * sa_risk
        base_risk = weighted_sum / base_sum

        # Blend with EMA if available
        if ema_weight > 0:
            final_risk = (1.0 - ema_weight) * base_risk + ema_weight * ema_risk
        else:
            final_risk = base_risk

        final_risk = min(1.0, max(0.0, final_risk))

        # Hard overrides
        if is_blacklisted:
            final_risk = max(0.75, final_risk)
        if dryrun_failed:
            final_risk = max(0.65, final_risk)

        return round(final_risk, 6)

    def _step8_final_ranking(
        self,
        scored_pools: List[ScoredPool],
        limit: int
    ) -> List[ScoredPool]:
        """
        Step 8: Sort by composite score, deduplicate by instance type, and assign ranks.

        Deduplication ensures each node on the cluster uses a DIFFERENT instance type
        to avoid risk concentration (e.g., all nodes on m5.xlarge).

        Sorting priority:
        1. ML composite score (primary)
        2. Predicted savings (tie-breaker when scores are equal)

        Returns top N diverse pools (limit).
        """
        # Sort by ML composite score (primary), then predicted savings, then lowest spot price
        # When ML scores are tied, cheapest absolute spot price = most savings vs any on-demand baseline
        # e.g. c5.large ($0.0255) ranks above m5.large ($0.0288), m5.2xlarge ($0.1152) ranks last
        def _sort_key(p):
            return (p.ml_score, p.predicted_savings, -p.pool.spot_price)

        sorted_pools = sorted(scored_pools, key=_sort_key, reverse=True)

        # Deduplicate: keep only the highest-scored pool per unique instance type
        seen_types = set()
        diverse_pools = []
        for pool in sorted_pools:
            if pool.pool.instance_type not in seen_types:
                diverse_pools.append(pool)
                seen_types.add(pool.pool.instance_type)

        # Assign ranks to top N diverse pools
        result = diverse_pools[:limit]
        for i, pool in enumerate(result, start=1):
            pool.rank = i

        logger.info(
            f"Step 8: {len(sorted_pools)} scored → {len(diverse_pools)} unique types → top {len(result)}"
        )
        return result

    def _step9_post_score_capacity_check(
        self, scored_pools: List[ScoredPool], region: str
    ) -> List[ScoredPool]:
        """Post-scoring capacity check: validate top 10 candidates only via DescribeInstanceTypeOfferings."""
        from botocore.exceptions import ClientError  # kept for except clause below

        active_clusters = int(self.redis.get("spot:active_cluster_count") or 1)
        MAX_DRYRUN_PER_HOUR = min(200, max(25, active_clusters * 2))
        PER_CLUSTER_CAP = 5
        TARGET_VALID = 10

        dryrun_key = f"spot:dryrun_count:{region}"
        current_count = int(self.redis.get(dryrun_key) or 0)
        remaining_budget = MAX_DRYRUN_PER_HOUR - current_count

        if remaining_budget <= 0:
            logger.warning(f"DryRun budget exhausted for {region} (used {current_count}/{MAX_DRYRUN_PER_HOUR})")
            # Retry: reuse recently-cached validation results from Redis
            _reused = 0
            for p in scored_pools[:TARGET_VALID]:
                _vk = f"spot:validated:{region}:{p.pool.instance_type}:{p.pool.az}"
                _cached_ts = self.redis.get(_vk) if self.redis else None
                if _cached_ts:
                    p.capacity_status = "validated"
                    p.capacity_validated_at = _cached_ts
                    _reused += 1
                else:
                    p.capacity_status = "unvalidated"
                    p.capacity_validated_at = None
            if self.redis:
                self.redis.incr("spot:metrics:dryrun_starvation_ratio")
            if _reused:
                logger.info(f"DryRun starvation: reused {_reused}/{TARGET_VALID} cached validations for {region}")
            return scored_pools[:TARGET_VALID]

        validated = []
        now = datetime.utcnow()

        for pool in scored_pools:
            if len(validated) >= TARGET_VALID or remaining_budget <= 0:
                break

            # Per-cluster fairness cap check
            cluster_id = pool.requesting_cluster_id if hasattr(pool, 'requesting_cluster_id') and pool.requesting_cluster_id else "default"
            cluster_dryrun_key = f"spot:dryrun_count:{region}:{cluster_id}"
            cluster_count = int(self.redis.get(cluster_dryrun_key) or 0)
            if cluster_count >= PER_CLUSTER_CAP:
                logger.debug(f"Skipping {pool.pool.instance_type}:{pool.pool.az} — cluster {cluster_id} at cap ({cluster_count}/{PER_CLUSTER_CAP})")
                continue

            try:
                # Use DescribeInstanceTypeOfferings instead of RunInstances DryRun.
                # RunInstances DryRun requires ImageId (causing ParamValidationError),
                # making every pool fail the check. DescribeInstanceTypeOfferings
                # directly reports which instance types are offered in each AZ.
                ec2 = self._get_ec2_client(region)
                _offerings_resp = ec2.describe_instance_type_offerings(
                    LocationType="availability-zone",
                    Filters=[
                        {"Name": "instance-type", "Values": [pool.pool.instance_type]},
                        {"Name": "location", "Values": [pool.pool.az]},
                    ],
                )
                _offered = bool(_offerings_resp.get("InstanceTypeOfferings"))
                if _offered:
                    pool.capacity_status = "validated"
                    pool.capacity_validated_at = now.isoformat()
                    validated.append(pool)
                    # Cache validation result for starvation retry (1 hour TTL)
                    try:
                        _vk = f"spot:validated:{region}:{pool.pool.instance_type}:{pool.pool.az}"
                        self.redis.setex(_vk, 3600, now.isoformat())
                    except Exception:
                        pass
                    logger.debug(f"Offering PASS: {pool.pool.instance_type}:{pool.pool.az}")
                else:
                    # Not offered — mark unvalidated (do NOT blacklist; offering availability
                    # varies by account/credentials and a false-negative here would
                    # permanently remove valid pools from rankings).
                    pool.capacity_status = "unvalidated"
                    logger.debug(f"Offering not confirmed for {pool.pool.instance_type}:{pool.pool.az} — marking unvalidated")
            except Exception as e:
                logger.error(f"DryRun exception for {pool.pool.instance_type}:{pool.pool.az}: {e}")
                if hasattr(self, 'db') and self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass
                pool.capacity_status = "unvalidated"
                continue

            # Increment budget counters
            remaining_budget -= 1
            count = self.redis.incr(dryrun_key)
            if count == 1:
                self.redis.expire(dryrun_key, 3600)  # 1 hour

            if cluster_id:
                ck_count = self.redis.incr(cluster_dryrun_key)
                if ck_count == 1:
                    self.redis.expire(cluster_dryrun_key, 3600)

        logger.debug(f"DryRun validated {len(validated)}/{TARGET_VALID} pools (budget: {MAX_DRYRUN_PER_HOUR - current_count - len(validated)}/{MAX_DRYRUN_PER_HOUR} remaining)")

        # FALLBACK: If no pools validated (e.g., all DryRun failed due to missing params),
        # return top pools anyway marked as "unvalidated" so UI can still show rankings
        if len(validated) == 0 and len(scored_pools) > 0:
            logger.debug(f"No pools validated via DryRun - returning top {TARGET_VALID} as unvalidated")
            for pool in scored_pools[:TARGET_VALID]:
                pool.capacity_status = "unvalidated"
                pool.capacity_validated_at = None
            return scored_pools[:TARGET_VALID]

        return validated

    def _get_ec2_client(self, region: str):
        """Get boto3 EC2 client for given region."""
        import boto3
        from backend.models.system_config import SystemConfig

        # Get AWS credentials from system config
        access_key = self.db.query(SystemConfig).filter(
            SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY"
        ).first()
        secret_key = self.db.query(SystemConfig).filter(
            SystemConfig.key == "PLATFORM_AWS_SECRET"
        ).first()

        if not access_key or not secret_key or not access_key.value or not secret_key.value:
            raise ValueError("AWS credentials not configured in system_config")

        return boto3.client(
            'ec2',
            region_name=region,
            aws_access_key_id=access_key.value,
            aws_secret_access_key=secret_key.value
        )

    def _estimate_instance_price(self, instance_type: str) -> float:
        """
        Estimate on-demand hourly price based on instance type.
        Used as fallback when pricing data is unavailable.
        """
        # Parse instance family and size
        parts = instance_type.split('.')
        if len(parts) != 2:
            return 0.10  # Default fallback

        family, size = parts

        # Size multipliers (relative to base)
        size_multipliers = {
            'nano': 0.25, 'micro': 0.5, 'small': 1.0, 'medium': 2.0,
            'large': 4.0, 'xlarge': 8.0, '2xlarge': 16.0, '3xlarge': 24.0,
            '4xlarge': 32.0, '6xlarge': 48.0, '8xlarge': 64.0,
            '9xlarge': 72.0, '12xlarge': 96.0, '16xlarge': 128.0,
            '18xlarge': 144.0, '24xlarge': 192.0, '32xlarge': 256.0
        }

        # Family base prices ($ per hour for .large equivalent) — accurate AWS ap-south-1 pricing
        family_base_prices = {
            't2': 0.023, 't3': 0.0832, 't3a': 0.0752, 't4g': 0.0672,
            'm5': 0.096, 'm5a': 0.086, 'm5n': 0.119, 'm6i': 0.096, 'm6a': 0.086, 'm6g': 0.077,
            'c5': 0.085, 'c5a': 0.077, 'c5n': 0.108, 'c6i': 0.085, 'c6a': 0.077, 'c6g': 0.068,
            'r5': 0.126, 'r5a': 0.113, 'r5n': 0.149, 'r6i': 0.126, 'r6a': 0.113, 'r6g': 0.101,
            'i3': 0.156, 'i3en': 0.226, 'i4i': 0.182,
            'g4dn': 0.526, 'g5': 1.006, 'p3': 3.060, 'p4d': 32.77
        }

        base_price = family_base_prices.get(family, 0.10)
        multiplier = size_multipliers.get(size, 4.0)  # Default to large

        return base_price * (multiplier / 4.0)  # Normalize to large=1.0

    def _fallback_scoring(self, pools: List[InstancePool]) -> List[ScoredPool]:
        """Fallback scoring when ONNX models are unavailable."""
        from backend.core.scoring import compute_expected_value
        scored_pools = []
        timestamp = datetime.utcnow()

        for pool in pools:
            # Simple heuristic: Higher headroom = better savings
            headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price if pool.ondemand_price > 0 else 0.5
            predicted_savings = headroom
            # Low risk estimate based on spot advisor rank (lower rank = safer)
            risk_probability = pool.spot_advisor_rank / 5.0 if pool.spot_advisor_rank <= 5 else 0.5

            final_score = compute_expected_value(predicted_savings, risk_probability)

            scored_pools.append(ScoredPool(
                pool=pool,
                predicted_savings=predicted_savings,
                risk_probability=risk_probability,
                ml_score=final_score,
                is_flagged=False,
                rank=0,
                timestamp=timestamp
            ))

        return scored_pools

    def _check_aws_capacity(self, instance_type: str, az: str, region: str) -> bool:
        """
        Check if AWS has capacity for this instance type in the given AZ.

        Uses EC2 RunInstances --dry-run API call to verify capacity.

        Args:
            instance_type: EC2 instance type (e.g., 'm5.large')
            az: Availability zone (e.g., 'aps1-az1')
            region: AWS region (e.g., 'ap-south-1')

        Returns:
            True if capacity available, False otherwise
        """
        try:
            import boto3
            from backend.models.system_config import SystemConfig
            from backend.core.aws_rate_limiter import AWSAPIRateLimiter

            # Get AWS credentials from system config
            access_key = self.db.query(SystemConfig).filter(
                SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY"
            ).first()
            secret_key = self.db.query(SystemConfig).filter(
                SystemConfig.key == "PLATFORM_AWS_SECRET"
            ).first()

            if not access_key or not secret_key or not access_key.value or not secret_key.value:
                logger.warning("AWS credentials not configured, assuming capacity exists")
                return True

            # Rate limit AWS API calls
            rate_limiter = AWSAPIRateLimiter.for_capacity_check("default")
            rate_limiter.acquire()

            # Create EC2 client
            ec2 = boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value
            )

            # Try dry-run launch to check capacity
            # Note: We're just checking if the call succeeds, not actually launching
            response = ec2.run_instances(
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                DryRun=True,
                Placement={'AvailabilityZone': az}
            )

            # If we get here without exception, capacity exists
            return True

        except boto3.exceptions.Boto3Error as e:
            error_code = e.response.get('Error', {}).get('Code', '') if hasattr(e, 'response') else ''

            # DryRunOperation means the dry-run was successful (capacity exists)
            if error_code == 'DryRunOperation':
                return True

            # InsufficientInstanceCapacity means no capacity
            if error_code == 'InsufficientInstanceCapacity':
                logger.info(f"No capacity for {instance_type} in {az}")
                return False

            # Unsupported instance type or other errors - assume capacity exists
            logger.warning(f"Capacity check ambiguous for {instance_type}/{az}: {error_code}")
            return True

        except Exception as e:
            logger.warning(f"Capacity check failed for {instance_type}/{az}: {e}")
            # On error, assume capacity exists to not block rankings
            return True

    def _cache_rankings(self, ranked_pools: List[ScoredPool]):
        """Cache ranked pools in Redis with 1-hour TTL (matches model prediction horizon)."""
        try:
            cache_key = "ascpai:pool_rankings"
            cache_data = [
                {
                    "instance_type": p.pool.instance_type,
                    "az": p.pool.az,
                    "predicted_savings": p.predicted_savings,
                    "risk_probability": p.risk_probability,
                    "ml_score": p.ml_score,
                    "rank": p.rank,
                    "is_flagged": p.is_flagged
                }
                for p in ranked_pools
            ]

            self.redis.setex(
                cache_key,
                3600,  # 1-hour TTL (matches model prediction horizon)
                json.dumps(cache_data)
            )
        except Exception as e:
            logger.error(f"Failed to cache rankings: {e}")

    # Helper methods for data retrieval

    def _get_region_azs(self, region: str) -> List[str]:
        """Get availability zones for a region (human-readable AZ names matching spot_price_history)."""
        # Return human-readable AZ names (e.g. ap-south-1a) to match SpotPriceHistory keys
        return [f"{region}a", f"{region}b", f"{region}c"]

    def _get_spot_advisor_data(self) -> Dict[str, int]:
        """
        Get AWS Spot Advisor frequency rankings from database.

        Returns: Dict mapping "instance_type:az" to interruption_index (0-4)
        """
        try:
            from backend.models.pricing import SpotAdvisorData

            # Query only Linux spot advisor data (filter out Windows platform data)
            advisor_records = self.db.query(SpotAdvisorData).filter(
                SpotAdvisorData.os_type == 'Linux'
            ).all()

            # Build lookup dict keyed as "instance_type:region"
            advisor_data = {}
            for record in advisor_records:
                advisor_key = f"{record.instance_type}:{record.region}"
                advisor_data[advisor_key] = record.interruption_index

            logger.info(f"Loaded {len(advisor_data)} Spot Advisor rankings from database")
            return advisor_data

        except Exception as e:
            logger.warning(f"Failed to load Spot Advisor data: {e}")
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            return {}

    def _ensure_spot_advisor_fresh(self, region: str) -> None:
        """
        Ensure Spot Advisor data exists and is not stale for the given region.
        Issue #28: Check spot:advisor:last_scraped key.
          >6h old  → warn
          >24h old → trigger inline re-scrape (same as missing data)
        If no records exist, trigger an inline scrape from AWS.
        """
        try:
            from backend.models.pricing import SpotAdvisorData

            # Issue #28: Staleness gate via Redis timestamp
            try:
                _last_scraped_raw = self.redis.get("spot:advisor:last_scraped")
                if _last_scraped_raw:
                    _last_scraped_str = (
                        _last_scraped_raw.decode("utf-8")
                        if isinstance(_last_scraped_raw, bytes)
                        else _last_scraped_raw
                    )
                    _last_scraped = datetime.fromisoformat(_last_scraped_str)
                    _age_h = (datetime.utcnow() - _last_scraped).total_seconds() / 3600
                    if _age_h > 24:
                        logger.warning(
                            f"[SPOT-ADVISOR] Data is {_age_h:.1f}h old (>24h threshold) — "
                            f"triggering inline re-scrape"
                        )
                        from backend.scrapers.spot_advisor_scraper import scrape_spot_advisor_data
                        result = scrape_spot_advisor_data()
                        logger.info(f"[SPOT-ADVISOR] Re-scrape complete: {result.get('status')}")
                        self.db.expire_all()
                        return
                    elif _age_h > 6:
                        logger.warning(
                            f"[SPOT-ADVISOR] Data is {_age_h:.1f}h old — eviction scores may "
                            f"be stale (>6h). Will re-scrape after 24h."
                        )
            except Exception as _staleness_err:
                logger.debug(f"[SPOT-ADVISOR] Staleness check skipped: {_staleness_err}")

            count = self.db.query(SpotAdvisorData).filter(
                SpotAdvisorData.region == region,
                SpotAdvisorData.os_type == 'Linux'
            ).count()

            if count == 0:
                logger.warning(
                    f"[SPOT-ADVISOR] No data found for region={region} — "
                    f"triggering inline scrape from AWS Spot Advisor API"
                )
                from backend.scrapers.spot_advisor_scraper import scrape_spot_advisor_data
                result = scrape_spot_advisor_data()
                logger.info(
                    f"[SPOT-ADVISOR] Inline scrape complete: {result.get('status')} "
                    f"({result.get('stats', {}).get('records_created', 0)} records created)"
                )
                # Refresh DB session to see new data
                self.db.expire_all()
            else:
                logger.info(f"[SPOT-ADVISOR] {count} records present for region={region}")

        except Exception as e:
            logger.error(f"[SPOT-ADVISOR] Freshness check failed: {e}")
            return {}

    # Hardcoded accurate on-demand hourly prices (ap-south-1, USD/hr).
    # Used as final fallback when OnDemandPricing table is empty and API call fails.
    # Prevents `ondemand = spot * 3.0` which creates constant 67% headroom for all pools.
    _ONDEMAND_FALLBACK: Dict[str, float] = {
        't3.nano': 0.0058, 't3.micro': 0.0116, 't3.small': 0.0232, 't3.medium': 0.0464,
        't3.large': 0.0928, 't3.xlarge': 0.1856, 't3.2xlarge': 0.3712,
        't3a.nano': 0.0052, 't3a.micro': 0.0104, 't3a.small': 0.0209, 't3a.medium': 0.0418,
        't3a.large': 0.0836, 't3a.xlarge': 0.1672, 't3a.2xlarge': 0.3344,
        't4g.nano': 0.0046, 't4g.micro': 0.0092, 't4g.small': 0.0184, 't4g.medium': 0.0368,
        't4g.large': 0.0736, 't4g.xlarge': 0.1472, 't4g.2xlarge': 0.2944,
        'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
        'm5a.large': 0.0864, 'm5a.xlarge': 0.1728, 'm5a.2xlarge': 0.3456,
        'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768,
        'm6a.large': 0.0864, 'm6a.xlarge': 0.1728, 'm6a.2xlarge': 0.3456,
        'm7i.large': 0.1008, 'm7i.xlarge': 0.2016, 'm7i.2xlarge': 0.4032,
        'm7a.large': 0.096, 'm7a.xlarge': 0.192, 'm7a.2xlarge': 0.384,
        'c5.large': 0.085, 'c5.xlarge': 0.170, 'c5.2xlarge': 0.340, 'c5.4xlarge': 0.680,
        'c6i.large': 0.085, 'c6i.xlarge': 0.170, 'c6i.2xlarge': 0.340,
        'c6a.large': 0.0765, 'c6a.xlarge': 0.153, 'c6a.2xlarge': 0.306,
        'c7i.large': 0.08925, 'c7i.xlarge': 0.1785, 'c7i.2xlarge': 0.357,
        'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008,
        'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504,
        'r7i.large': 0.1323, 'r7i.xlarge': 0.2646, 'r7i.2xlarge': 0.5292,
        'i3.large': 0.156, 'i3.xlarge': 0.312, 'i3.2xlarge': 0.624, 'i3.4xlarge': 1.248,
        'g4dn.xlarge': 0.526, 'g4dn.2xlarge': 0.752, 'g4dn.4xlarge': 1.204,
        'p3.2xlarge': 3.06, 'p3.8xlarge': 12.24,
    }

    def _get_pricing_data(self, region: str) -> Dict[str, Dict[str, float]]:
        """
        Get current spot and on-demand prices.

        Returns: Dict mapping "instance_type:az" to {"spot": float, "ondemand": float}

        Priority order (fast-path first):
        1. Redis spot_price:{region}:{az}:{type} keys (written by pricing worker, ~1991 entries)
        2. DB SpotPriceHistory ONLY if Redis is empty (164K rows — expensive, avoid)
        OD prices: Redis od_price/ondemand_price keys → DB OnDemandPricing → _ONDEMAND_FALLBACK
        AWS Pricing API is NEVER called inline (too slow for 825+ pools).
        """
        pricing_data = {}

        # ── Fast path: Redis spot_price:* keys ────────────────────────────────
        if hasattr(self, 'redis') and self.redis:
            try:
                # Build OD lookup from Redis (od_price and ondemand_price keys)
                _od_redis: Dict[str, float] = {}
                for _od_key_fmt in [f"od_price:{region}:*", f"ondemand_price:{region}:*"]:
                    _od_cur = 0
                    while True:
                        _od_cur, _od_keys = self.redis.scan(_od_cur, match=_od_key_fmt, count=200)
                        for _ok in _od_keys:
                            try:
                                _ok_str = _ok.decode() if isinstance(_ok, bytes) else _ok
                                _itype = _ok_str.rsplit(':', 1)[-1]
                                _raw = self.redis.get(_ok)
                                if _raw:
                                    _od_redis[_itype] = float(_raw)
                            except Exception:
                                pass
                        if _od_cur == 0:
                            break

                cursor = 0
                while True:
                    cursor, keys = self.redis.scan(
                        cursor, match=f"spot_price:{region}:*", count=500
                    )
                    for key in keys:
                        try:
                            raw = self.redis.get(key)
                            if not raw:
                                continue
                            key_str = key.decode() if isinstance(key, bytes) else key
                            parts = key_str.split(':')
                            if len(parts) >= 4:
                                _az = parts[2]
                                _itype = ':'.join(parts[3:])
                                _data = json.loads(raw)
                                _spot = float(_data.get('price', 0) or 0)
                                if _spot <= 0:
                                    continue
                                # OD: Redis → _ONDEMAND_FALLBACK → skip pool (no fabricated pricing)
                                _od = (
                                    _od_redis.get(_itype)
                                    or self._ONDEMAND_FALLBACK.get(_itype)
                                )
                                if not _od:
                                    logger.debug(f"[pricing_data] Skipping {_itype}:{_az}: no OD price available")
                                    continue
                                pricing_data[f"{_itype}:{_az}"] = {"spot": _spot, "ondemand": _od}
                        except Exception:
                            pass
                    if cursor == 0:
                        break

                if pricing_data:
                    logger.info(
                        f"[pricing_data] Redis fast-path: {len(pricing_data)} pools for {region}"
                    )
                    return pricing_data
            except Exception as _redis_err:
                logger.warning(f"[pricing_data] Redis fast-path failed: {_redis_err}")

        # ── Slow path: DB SpotPriceHistory (only reached if Redis empty) ──────
        try:
            from backend.models.pricing import SpotPriceHistory, OnDemandPricing
            from datetime import datetime, timedelta

            # Load only one row per (instance_type, az) — most recent price
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            from sqlalchemy import func as _sqlfunc
            latest_subq = (
                self.db.query(
                    SpotPriceHistory.instance_type,
                    SpotPriceHistory.availability_zone,
                    _sqlfunc.max(SpotPriceHistory.timestamp).label('max_ts'),
                )
                .filter(
                    SpotPriceHistory.region == region,
                    SpotPriceHistory.timestamp >= one_hour_ago,
                )
                .group_by(SpotPriceHistory.instance_type, SpotPriceHistory.availability_zone)
                .subquery()
            )
            spot_prices = (
                self.db.query(SpotPriceHistory)
                .join(latest_subq, (
                    (SpotPriceHistory.instance_type == latest_subq.c.instance_type) &
                    (SpotPriceHistory.availability_zone == latest_subq.c.availability_zone) &
                    (SpotPriceHistory.timestamp == latest_subq.c.max_ts)
                ))
                .all()
            )

            # OD lookup from DB
            od_map: Dict[str, float] = {}
            od_rows = self.db.query(OnDemandPricing).filter(OnDemandPricing.region == region).all()
            for r in od_rows:
                od_map[r.instance_type] = float(r.price)

            for sp in spot_prices:
                key = f"{sp.instance_type}:{sp.availability_zone}"
                _spot = float(sp.price)
                _od = (
                    od_map.get(sp.instance_type)
                    or self._ONDEMAND_FALLBACK.get(sp.instance_type)
                )
                if not _od:
                    logger.debug(f"[pricing_data] Skipping {sp.instance_type}:{sp.availability_zone}: no OD price available")
                    continue
                pricing_data[key] = {"spot": _spot, "ondemand": _od}

            logger.info(f"Loaded pricing data for {len(pricing_data)} instance/AZ combinations")
            return pricing_data

        except Exception as e:
            logger.error(f"Failed to load pricing data: {e}")
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            return {}


    # ========================================================================
    # SIZE-CONSTRAINED RANKING (Unified Optimizer Coordination)
    # ========================================================================

    def rank_pools_for_size(
        self,
        vcpu: int,
        memory_gb: float,
        region: str = "ap-south-1",
        allowed_families: Optional[List[str]] = None,
        architecture: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ScoredPool]:
        """
        Rank pools constrained to a specific instance size.

        Used by the Unified Optimizer Coordinator to re-evaluate Spot ML
        within the size envelope proposed by rightsizing.

        This implements the coordination pattern from problems.md:
        - Rightsizing proposes new size (e.g., 2 vCPU / 4 GB)
        - Coordinator calls this method to get best pools for that size
        - Combined EV calculation compares options

        Args:
            vcpu: Exact vCPU count (or use range vcpu ± 1 for flexibility)
            memory_gb: Exact memory in GB (or use range memory ± 2 for flexibility)
            region: AWS region
            allowed_families: Optional instance family filter (e.g., ["m5", "m6i"])
            architecture: Optional architecture filter (default: ["amd64", "arm64"])
            limit: Maximum number of pools to return

        Returns:
            List of scored pools matching the size constraint

        Example:
            # Rightsizing proposes 2 vCPU / 4 GB
            pools = service.rank_pools_for_size(
                vcpu=2,
                memory_gb=4,
                region="us-east-1",
                allowed_families=["m5", "m6i"],
                limit=5
            )
            # Returns: m5.large, m6i.large, etc. (all 2 vCPU / 4 GB)
        """
        # Create size-constrained template with flexible range (±1 vCPU, ±2 GB)
        # This allows near-matches in case exact size isn't available
        vcpu_min = max(1, vcpu)
        vcpu_max = vcpu + 1
        memory_min = max(1, int(memory_gb - 2))
        memory_max = int(memory_gb + 2)

        template = NodeTemplate(
            architecture=architecture or ["amd64", "arm64"],
            vcpu_range=(vcpu_min, vcpu_max),
            memory_range=(memory_min, memory_max),
            allowed_families=allowed_families,
            allowed_sizes=None,  # Allow all sizes within the vCPU/memory range
            allowed_azs=None,  # Allow all AZs
            excluded_instance_types=None
        )

        # Use existing rank_pools pipeline
        ranked_pools = self.rank_pools(
            node_template=template,
            region=region,
            limit=limit
        )

        # Filter to exact or near-exact matches (prefer exact size)
        # Sort by how close to target size (exact matches first)
        def size_distance(pool: ScoredPool) -> Tuple[int, int]:
            vcpu_diff = abs(pool.pool.vcpu - vcpu)
            memory_diff = abs(pool.pool.memory_gb - memory_gb)
            return (vcpu_diff, memory_diff)

        ranked_pools_sorted = sorted(ranked_pools, key=size_distance)

        logger.info(
            f"Size-constrained ranking: {len(ranked_pools_sorted)} pools for "
            f"{vcpu} vCPU / {memory_gb} GB in region {region}"
        )

        return ranked_pools_sorted[:limit]

    def get_best_pool_for_size(
        self,
        vcpu: int,
        memory_gb: float,
        region: str = "ap-south-1",
        allowed_families: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Get single best pool for a specific size.

        Convenience method for coordinator to get the top recommendation.

        Returns:
            Dict with pool info or None if no pools found
        """
        pools = self.rank_pools_for_size(
            vcpu=vcpu,
            memory_gb=memory_gb,
            region=region,
            allowed_families=allowed_families,
            limit=1
        )

        if not pools:
            return None

        best = pools[0]
        return {
            "instance_type": best.pool.instance_type,
            "az": best.pool.az,
            "vcpu": best.pool.vcpu,
            "memory_gb": best.pool.memory_gb,
            "spot_price": best.pool.spot_price,
            "ondemand_price": best.pool.ondemand_price,
            "predicted_savings": best.predicted_savings,
            "risk_probability": best.risk_probability,
            "ml_score": best.ml_score,
            "pool_key": f"{best.pool.instance_type}:{best.pool.az}"
        }

    def rank_pools_for_node(
        self,
        node_info: dict,
        cluster_id: str,
        region: str,
        include_dynamic_filters: bool = True,
        force_type: Optional[str] = None,
    ) -> List[dict]:
        """
        Unified ranked pool list for a specific node.

        Single source of truth used by:
        - GET /alternatives UI endpoint
        - Rebalancing action creation
        - Execution-time pool re-ranking in auto_rebalancer

        Sort key: expected_value = savings_pct × (1 - risk_probability), DESC
        where savings_pct is relative to the source node's on-demand price.

        Args:
            node_info: Dict with keys: instance_type, az, od_price (optional),
                       resource_profile (optional dict with min_vcpu_required,
                       min_memory_required, architecture).
            cluster_id: Cluster ID (used to load settings and occupancy).
            region: AWS region.
            include_dynamic_filters: When True, apply occupancy, family allow/block,
                                      allowed zones, and cross-AZ constraints from
                                      the cluster's NodeTemplate.
            force_type: Restrict output to this instance type only (for S2S same-type).

        Returns:
            List of pool dicts sorted by expected_value DESC.
        """
        import json as _json
        from backend.core.redis_client import key_market_view_cache, key_global_pool_rankings

        # ── Load cluster settings ─────────────────────────────────────────────
        risk_ceiling = 0.25
        tradeoff_pct = 0.20
        arch_pref = 'both'
        diversify_enabled = False
        _min_savings_setting = 0
        try:
            from backend.models.cluster import ClusterOptimizationSettings, OptimizationStrategy
            _cos = self.db.query(ClusterOptimizationSettings).filter_by(cluster_id=cluster_id).first()
            _os = self.db.query(OptimizationStrategy).filter_by(cluster_id=cluster_id).first()
            if _cos:
                arch_pref = getattr(_cos, 'architecture_preference', 'both') or 'both'
                diversify_enabled = bool(getattr(_cos, 'diversify_pools', False))
            if _os:
                risk_ceiling = (getattr(_os, 'risk_ceiling_percent', 25) or 25) / 100.0
                tradeoff_pct = (getattr(_os, 'risk_savings_tradeoff_pct', 20) or 20) / 100.0
                # N2 fix: Load min_savings_percent so we can enforce it in the filter loop
                _min_savings_setting = getattr(_os, 'min_savings_percent', 0) or 0
        except Exception:
            pass
        # Apply regional market factor to risk ceiling (same as auto_rebalancer)
        try:
            _mf_raw = self.redis.get(f"market_factor:{region}")
            if _mf_raw:
                risk_ceiling *= max(0.8, min(1.2, float(_mf_raw)))
        except Exception:
            pass

        # ── Load NodeTemplate constraints ─────────────────────────────────────
        allowed_families: Optional[List[str]] = None
        excluded_families: List[str] = ["metal", "g", "p", "trn", "inf", "i"]
        allowed_zones: Optional[List[str]] = None
        cross_az_rebalance: bool = True
        if include_dynamic_filters:
            try:
                from backend.models.node_template import ClusterTemplateMapping
                _ctm = self.db.query(ClusterTemplateMapping).filter_by(
                    cluster_id=cluster_id, is_default=True
                ).first()
                if _ctm and _ctm.version and _ctm.version.constraints_json:
                    _tc = _ctm.version.constraints_json
                    if isinstance(_tc, dict):
                        _af = _tc.get('allowed_families') or []
                        if _af:
                            allowed_families = list(_af)
                        _ef = _tc.get('excluded_families')
                        if _ef:
                            excluded_families = list(_ef)
                        _az_list = _tc.get('allowed_zones') or []
                        if _az_list:
                            allowed_zones = list(_az_list)
                        cross_az_rebalance = bool(_tc.get('cross_az_rebalance', True))
            except Exception:
                pass

        # ── Derive node requirements ──────────────────────────────────────────
        instance_type = node_info.get('instance_type', '')
        source_az = node_info.get('az', '')
        rp = node_info.get('resource_profile', {})
        min_vcpu = int(rp.get('min_vcpu_required', 0) or 0)
        min_memory_gb = float(rp.get('min_memory_required', 0.0) or 0.0)
        required_arch = rp.get('architecture')

        if (min_vcpu <= 0 or min_memory_gb <= 0) and instance_type:
            try:
                from backend.workers.tasks.cache_builder import _lookup_specs
                _v, _m, _a, _is_fallback = _lookup_specs(instance_type)
                if _is_fallback:
                    logger.critical(
                        "Instance type %s not in spec table — cannot determine vCPU/memory floor. "
                        "Skipping pool ranking for this node to prevent undersized replacement. "
                        "Add the type to _FALLBACK_SPECS in cache_builder.py to re-enable.",
                        instance_type
                    )
                    return []
                if min_vcpu <= 0 and _v:
                    min_vcpu = int(_v)
                if min_memory_gb <= 0 and _m:
                    min_memory_gb = float(_m)
                if not required_arch and _a:
                    required_arch = _a
            except Exception:
                pass

        # N9 fix: If min_vcpu is still 0 after lookup, abort ranking entirely.
        # A zero floor would allow any pool to pass, potentially replacing a
        # 72-vCPU node with a 2-vCPU instance (causing OOMKill/throttling).
        if min_vcpu <= 0:
            logger.critical(
                "[rank_pools_for_node] min_vcpu=0 for node %s (type=%s) — "
                "refusing to rank pools to prevent undersized replacement",
                node_info.get('node_name', '?'), instance_type,
            )
            return []

        # Architecture override from cluster preference
        if arch_pref == 'amd64':
            required_arch = 'amd64'
        elif arch_pref == 'arm64':
            required_arch = 'arm64'
        elif arch_pref == 'both':
            required_arch = None  # allow all architectures through the filter

        # Source OD price (used for OD nodes and as fallback for spot nodes)
        node_od_price = float(node_info.get('od_price', 0) or 0)
        if node_od_price <= 0 and instance_type:
            try:
                from backend.workers.tasks.cache_builder import _lookup_od_price
                node_od_price = float(_lookup_od_price(self.redis, region, instance_type) or 0)
            except Exception:
                pass
        # Savings baseline: use actual current price (spot price for spot nodes).
        # For spot source nodes, savings should be relative to what the node is
        # currently paying, not the hypothetical OD price.
        _node_current_price = float(node_info.get('current_price', 0) or 0)
        _savings_baseline = _node_current_price if _node_current_price > 0 else node_od_price

        # ── Load pool cache ───────────────────────────────────────────────────
        raw = self.redis.get(key_market_view_cache(region))
        if not raw:
            raw = self.redis.get(key_global_pool_rankings(region))
        if not raw:
            logger.warning(
                f"[rank_pools_for_node] No pool cache for region={region} cluster={cluster_id}"
            )
            return []
        payload = _json.loads(raw)
        all_pools = payload.get('data', []) if isinstance(payload, dict) else payload

        # ── Load blacklist ────────────────────────────────────────────────────
        _blacklisted: set = set()
        try:
            _bl = self.redis.smembers("risky_pools")
            if _bl:
                _blacklisted = {(m.decode() if isinstance(m, bytes) else m) for m in _bl}
        except Exception:
            pass

        # ── Build occupied set (dynamic: running + pending instances in cluster) ──
        _occupied_pools: set = set()
        if include_dynamic_filters and diversify_enabled:
            try:
                from backend.models.instance import Instance
                _running = self.db.query(Instance.instance_type, Instance.az).filter(
                    Instance.cluster_id == cluster_id,
                    Instance.state.in_(['running', 'pending']),
                    Instance.instance_type.isnot(None),
                ).all()
                _occupied_pools = {
                    f"{r.instance_type}:{r.az}" for r in _running if r.instance_type and r.az
                }
                # Remove the source node's own pool so it remains eligible.
                # Without this, the best pool is excluded if the node already
                # runs it — making diversification drop the safest option.
                _source_pk = f"{instance_type}:{source_az}"
                _occupied_pools.discard(_source_pk)
            except Exception:
                pass

        # ── Score and filter pools ────────────────────────────────────────────
        results: List[dict] = []
        _seen_families: Dict[str, int] = {}  # for family diversification cap

        for p in all_pools:
            p = dict(p)
            itype = p.get('instance_type', '')
            az = p.get('az', '')

            # force_type gate
            if force_type and itype != force_type:
                continue

            # Blacklist
            pk = f"{itype}:{az}"
            if pk in _blacklisted:
                continue

            spot_price = float(p.get('spot_price', 0) or 0)
            if spot_price <= 0:
                continue

            # vCPU and memory floor
            pool_vcpu = int(p.get('vcpu', 0) or 0)
            pool_mem = float(p.get('memory_gb', 0.0) or 0.0)
            if pool_vcpu <= 0 or pool_mem <= 0:
                continue
            if min_vcpu > 0 and pool_vcpu < min_vcpu:
                continue
            if min_memory_gb > 0 and pool_mem < min_memory_gb:
                continue

            # Architecture filter
            pool_arch = (p.get('architecture') or 'amd64').lower()
            if required_arch:
                _ok_arch = (pool_arch == required_arch) or (
                    required_arch == 'amd64' and pool_arch == 'x86_64'
                )
                if not _ok_arch:
                    continue

            # Risk ceiling (prefer ml-blended risk_probability, fall back to AWS rate)
            aws_irr_pct = float(p.get('interruption_rate_pct', 15.0) or 15.0)
            pool_risk = float(p.get('risk_probability', aws_irr_pct / 100.0) or aws_irr_pct / 100.0)
            if pool_risk > 1.0:
                pool_risk /= 100.0
            if pool_risk > risk_ceiling:
                continue

            # Dynamic filters (template constraints + occupancy)
            if include_dynamic_filters:
                family = itype.split('.')[0] if '.' in itype else itype

                # Template: allowed/excluded families
                if allowed_families and family not in allowed_families:
                    continue
                if excluded_families and family in excluded_families:
                    continue

                # Template: allowed zones
                if allowed_zones and az not in allowed_zones:
                    continue

                # Template: cross-AZ restriction
                if not cross_az_rebalance and source_az and az != source_az:
                    continue

                # Occupancy (when diversify is enabled): skip pools already running
                if diversify_enabled and pk in _occupied_pools:
                    continue

            # Compute savings relative to the node's actual current price.
            # For OD nodes: _savings_baseline == node_od_price.
            # For spot nodes: _savings_baseline == current spot price (not OD price).
            if _savings_baseline > 0:
                savings_pct = (_savings_baseline - spot_price) / _savings_baseline
            else:
                savings_pct = float(p.get('predicted_savings', 0) or 0)

            # Only positive-savings pools (negative savings removed per unified design)
            if savings_pct < 0:
                continue

            # N2 fix: Enforce min_savings_percent from OptimizationStrategy.
            # savings_pct is a fraction (e.g. 0.20 = 20%), _min_savings_setting
            # is an integer percentage (e.g. 20 = 20%).
            if _min_savings_setting > 0 and savings_pct < (_min_savings_setting / 100.0):
                continue

            # Family diversification cap (moved AFTER savings/price filters so
            # oversized pools that fail on price don't consume family cap slots,
            # allowing affordable same-family pools through).
            if include_dynamic_filters and diversify_enabled:
                family = itype.split('.')[0] if '.' in itype else itype
                _seen_families[family] = _seen_families.get(family, 0) + 1
                if _seen_families[family] > 2:
                    continue

            ev = savings_pct * (1.0 - pool_risk)

            # Unified score (for display)
            _rep_mult = float(p.get('reputation_mult', 1.0) or 1.0)
            _cap_mult = 1.1 if bool(p.get('has_capacity')) else 1.0
            _uni_score = (savings_pct * 0.8) * (1.0 - pool_risk) * _rep_mult * _cap_mult

            # Derive spot_advisor_rank for display
            orig_sa_rank = p.get('spot_advisor_rank')
            if orig_sa_rank is None:
                if aws_irr_pct <= 5:
                    orig_sa_rank = 0
                elif aws_irr_pct <= 10:
                    orig_sa_rank = 1
                elif aws_irr_pct <= 15:
                    orig_sa_rank = 2
                elif aws_irr_pct <= 20:
                    orig_sa_rank = 3
                else:
                    orig_sa_rank = 4

            p['savings_pct'] = round(savings_pct * 100, 2)
            p['saving_pct'] = p['savings_pct']
            p['customer_savings_pct'] = p['savings_pct']
            p['expected_value'] = round(ev, 6)
            p['unified_score'] = round(_uni_score, 6)
            p['risk_probability'] = round(pool_risk, 4)
            p['interruption_rate_pct'] = aws_irr_pct
            p['spot_advisor_rank'] = int(orig_sa_rank)
            p['node_od_baseline'] = round(node_od_price, 6)
            p['spot_price_raw'] = spot_price
            results.append(p)

        # Sort by expected_value DESC (best first)
        results.sort(key=lambda x: x['expected_value'], reverse=True)

        # ── Rebalancer double-gate annotation ─────────────────────────────────
        # Run the exact same 4-pass selection logic as auto_rebalancer.py so the
        # UI shows which pools would actually be launched — not just which pass
        # the ML+risk filters. Each pool gets:
        #   rebalancer_eligible: bool — passes the gate (would be a valid launch target)
        #   rebalancer_pass: int 1-4 or null — which pass accepted it
        #   would_be_launched: bool — the single pool the rebalancer would pick this cycle
        #
        # Pass 1: spot < OD price AND risk < ceiling
        # Pass 2: spot <= cheapest + tradeoff*(OD-cheapest) AND risk < ceiling
        # Pass 3: risk override — node itself is risky, any safer pool accepted
        # Pass 4: OD→Spot fallback — any cheaper spot (OD nodes only)
        _gate_od_price = node_od_price if node_od_price > 0 else 0.10
        _valid_spot_prices = [p['spot_price_raw'] for p in results if p['spot_price_raw'] > 0]
        _cheapest_spot_price = min(_valid_spot_prices) if _valid_spot_prices else _gate_od_price * 0.3
        _max_tradeoff_price = _cheapest_spot_price + (_gate_od_price - _cheapest_spot_price) * tradeoff_pct

        # Initialise all pools as not eligible
        for p in results:
            p['rebalancer_eligible'] = False
            p['rebalancer_pass'] = None
            p['would_be_launched'] = False

        # Pass 1
        _pass1_pools = [
            p for p in results
            if (
                (p['spot_price_raw'] > 0 and p['spot_price_raw'] < _gate_od_price) or
                (p['spot_price_raw'] == 0 and (p.get('expected_value', 0) or 0) > 0.05)
            ) and p['risk_probability'] < risk_ceiling
        ]
        for p in _pass1_pools:
            p['rebalancer_eligible'] = True
            p['rebalancer_pass'] = 1

        # Pass 2 (tradeoff) — only for pools that didn't pass Pass 1
        if not _pass1_pools:
            _pass2_pools = [
                p for p in results
                if (
                    (p['spot_price_raw'] > 0 and p['spot_price_raw'] <= _max_tradeoff_price) or
                    p['spot_price_raw'] == 0
                ) and p['risk_probability'] < risk_ceiling
                and not p['rebalancer_eligible']
            ]
            for p in _pass2_pools:
                p['rebalancer_eligible'] = True
                p['rebalancer_pass'] = 2

        # Pass 3 (risk override) — only if passes 1+2 found nothing
        if not any(p['rebalancer_eligible'] for p in results):
            _node_risk_from_info = float(node_info.get('risk_score', 0) or 0)
            if _node_risk_from_info > risk_ceiling:
                for p in results:
                    if p['risk_probability'] < _node_risk_from_info:
                        p['rebalancer_eligible'] = True
                        p['rebalancer_pass'] = 3

        # Pass 4 (OD→Spot final fallback) — any pool cheaper than OD price
        if not any(p['rebalancer_eligible'] for p in results):
            for p in results:
                if p['spot_price_raw'] == 0 or p['spot_price_raw'] < _gate_od_price:
                    p['rebalancer_eligible'] = True
                    p['rebalancer_pass'] = 4

        # Mark the single pool the rebalancer would pick (top eligible by expected_value)
        _eligible = [p for p in results if p['rebalancer_eligible']]
        if _eligible:
            # Pick same way rebalancer does: first Pass-1 by expected_value, else lowest risk
            _p1 = [p for p in _eligible if p['rebalancer_pass'] == 1]
            if _p1:
                _p1[0]['would_be_launched'] = True
            else:
                # Pass 2/3/4: lowest risk wins
                _best = min(_eligible, key=lambda x: x['risk_probability'])
                _best['would_be_launched'] = True

        logger.info(
            f"[rank_pools_for_node] cluster={cluster_id} region={region} "
            f"node={instance_type} → {len(results)} eligible pools "
            f"({sum(1 for p in results if p['rebalancer_eligible'])} pass rebalancer gate, "
            f"dynamic_filters={include_dynamic_filters})"
        )
        return results


# ── Module-level helper functions for pool scoring / launch tracking ──────────


def estimate_az_interruption(
    instance_type: str,
    az: str,
    region: str,
    redis_client=None,
) -> Optional[float]:
    """
    Task 2.7 — AZ-level interruption rate estimation (3-layer model).

    Layer 1: AWS region-level base rate from spot_advisor:{region}:{type}:Linux
    Layer 2: AZ price premium adjustment (+1 tier if AZ price > 20% above region avg)
    Layer 3: Own historical interruption data from Redis (exponential moving average)

    Returns the combined interruption rate (0-25 scale) or None if unknown.
    """
    if redis_client is None:
        from backend.core.redis_client import get_redis_client
        redis_client = get_redis_client()

    # Layer 1: region-level base rate
    try:
        raw = redis_client.get(f"spot_advisor:{region}:{instance_type}:Linux")
        if not raw:
            return None
        data = json.loads(raw)
        idx = int(data.get("interruption_index", 4))
        _idx_to_pct = {0: 5.0, 1: 10.0, 2: 15.0, 3: 20.0, 4: 25.0}
        region_rate = _idx_to_pct.get(idx, 25.0)
    except Exception:
        return None

    # Layer 2: AZ price adjustment
    az_adjustment = 0.0
    try:
        az_price_raw = redis_client.get(f"spot_price:{region}:{az}:{instance_type}")
        if az_price_raw:
            az_price_data = json.loads(az_price_raw)
            az_price = float(az_price_data.get('price', 0))

            # Compute region avg as mean of available AZ prices for this type
            all_az_prices = []
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(
                    cursor, match=f"spot_price:{region}:*:{instance_type}", count=50
                )
                for k in keys:
                    try:
                        v = redis_client.get(k)
                        if v:
                            all_az_prices.append(float(json.loads(v).get('price', 0)))
                    except Exception:
                        pass
                if cursor == 0:
                    break

            if all_az_prices and az_price > 0:
                region_avg = sum(all_az_prices) / len(all_az_prices)
                if region_avg > 0:
                    price_ratio = az_price / region_avg
                    if price_ratio > 1.20:
                        az_adjustment = 1.0
                    elif price_ratio > 1.10:
                        az_adjustment = 0.5
    except Exception:
        pass

    # Layer 3: Own historical data (EMA)
    history_weight = 0.0
    own_rate = region_rate
    try:
        history_key = f"interruption_history:{region}:{az}:{instance_type}"
        history_raw = redis_client.get(history_key)
        if history_raw:
            history = json.loads(history_raw)
            own_rate = history.get('rate', region_rate)
            event_count = history.get('count', 0)
            history_weight = min(event_count / 100.0, 0.5)
    except Exception:
        pass

    aws_weight = 1.0 - history_weight
    combined = (region_rate + az_adjustment) * aws_weight + own_rate * history_weight
    return min(combined, 25.0)


def record_interruption_event(
    region: str,
    az: str,
    instance_type: str,
    redis_client=None,
):
    """
    Task 2.7 — Record a spot interruption event for a pool.

    Updates interruption_history:{region}:{az}:{instance_type} with an
    exponential moving average. Called by termination_monitor when a spot
    interruption is detected.

    History TTL: 7 days.
    """
    if redis_client is None:
        from backend.core.redis_client import get_redis_client
        redis_client = get_redis_client()

    history_key = f"interruption_history:{region}:{az}:{instance_type}"
    try:
        raw = redis_client.get(history_key)
        history = json.loads(raw) if raw else {"rate": 0.0, "count": 0}
        history["count"] += 1
        # EMA: each interruption event pushes rate toward 25 (max tier)
        history["rate"] = history["rate"] * 0.9 + 25.0 * 0.1
        redis_client.setex(history_key, 86400 * 7, json.dumps(history))
        logger.info(
            f"[pool_ranking] Recorded interruption event {region}/{az}/{instance_type} "
            f"count={history['count']} rate={history['rate']:.1f}"
        )
    except Exception as e:
        logger.warning(f"[pool_ranking] record_interruption_event failed: {e}")


def assign_risk_tier(interruption_rate_pct: float) -> int:
    """
    Assign a risk tier (0-4) based on interruption rate percentage.
    Uses RISK_TIER_THRESHOLDS = [0.05, 0.10, 0.15, 0.20].
    Tier 0 = safest (<5%), Tier 4 = riskiest (>20%).
    """
    from backend.core.config import RISK_TIER_THRESHOLDS
    rate = interruption_rate_pct / 100.0  # convert pct to fraction
    for i, threshold in enumerate(RISK_TIER_THRESHOLDS):
        if rate <= threshold:
            return i
    return len(RISK_TIER_THRESHOLDS)


def compute_capacity_score(vcpu: int, memory_gb: float) -> float:
    """Composite capacity score: vcpu + memory_gb / CAPACITY_SCORE_DIVISOR."""
    from backend.core.config import CAPACITY_SCORE_DIVISOR
    return vcpu + (memory_gb / CAPACITY_SCORE_DIVISOR)


def report_launch_attempt(pool_key: str):
    """Increment launch attempt counter for a pool in Redis."""
    try:
        from backend.core.redis_client import get_redis_client, key_pool_launch_attempts
        r = get_redis_client()
        k = key_pool_launch_attempts(pool_key)
        r.incr(k)
        r.expire(k, 86400)
    except Exception as e:
        logger.warning(f"[pool_ranking] report_launch_attempt failed: {e}")


def report_launch_failure(pool_key: str):
    """Increment launch failure counter for a pool in Redis."""
    try:
        from backend.core.redis_client import get_redis_client, key_pool_launch_failures, key_pool_launch_attempts
        from backend.core.config import LAUNCH_FAILURE_RATIO_THRESHOLD
        r = get_redis_client()
        k_fail = key_pool_launch_failures(pool_key)
        r.incr(k_fail)
        r.expire(k_fail, 86400)

        # Auto-blacklist if failure ratio exceeds threshold
        failures = int(r.get(k_fail) or 0)
        attempts = int(r.get(key_pool_launch_attempts(pool_key)) or 1)
        if attempts > 0 and (failures / attempts) >= LAUNCH_FAILURE_RATIO_THRESHOLD:
            blacklist_pool_temporary(pool_key)
            logger.warning(
                f"[pool_ranking] Auto-blacklisted {pool_key}: "
                f"{failures}/{attempts} = {failures/attempts:.0%} failure rate"
            )
    except Exception as e:
        logger.warning(f"[pool_ranking] report_launch_failure failed: {e}")


def report_launch_success(pool_key: str, uptime_hours: float = None):
    """
    Pillar 3 — Closed-Loop ML: record a successful launch outcome for a pool.

    Updates pool_reputation:{pool_key} in Redis with:
      - launch_success_rate (rolling window)
      - avg_uptime_hours (EMA)
      - last_success_at timestamp
    TTL: 7 days.
    """
    try:
        from backend.core.redis_client import get_redis_client
        import time
        r = get_redis_client()
        rep_key = f"pool_reputation:{pool_key}"
        raw = r.get(rep_key)
        rep = json.loads(raw) if raw else {
            "successes": 0, "attempts": 0, "avg_uptime_hours": None,
            "last_success_at": None,
        }
        rep["successes"] = rep.get("successes", 0) + 1
        rep["attempts"] = rep.get("attempts", 0) + 1
        rep["last_success_at"] = time.time()
        # EMA for uptime
        if uptime_hours is not None:
            prev = rep.get("avg_uptime_hours")
            if prev is None:
                rep["avg_uptime_hours"] = uptime_hours
            else:
                rep["avg_uptime_hours"] = prev * 0.8 + uptime_hours * 0.2
        r.setex(rep_key, 86400 * 7, json.dumps(rep))
    except Exception as e:
        logger.warning(f"[pool_ranking] report_launch_success failed: {e}")


def get_pool_reputation(pool_key: str, redis_client=None) -> dict:
    """
    Pillar 3 — Closed-Loop ML: get pool reputation metrics.

    Returns dict with:
      - launch_success_rate: float 0.0–1.0
      - avg_uptime_hours: float or None
      - reputation_multiplier: float 0.5–1.2 (for scoring)
    """
    try:
        if redis_client is None:
            from backend.core.redis_client import get_redis_client
            redis_client = get_redis_client()
        raw = redis_client.get(f"pool_reputation:{pool_key}")
        if not raw:
            # Also check failure counters for pools we've attempted but not succeeded
            from backend.core.redis_client import key_pool_launch_attempts, key_pool_launch_failures
            attempts = int(redis_client.get(key_pool_launch_attempts(pool_key)) or 0)
            failures = int(redis_client.get(key_pool_launch_failures(pool_key)) or 0)
            if attempts > 0:
                rate = max(0.0, (attempts - failures) / attempts)
                rep_mult = 0.5 + (rate * 0.7)  # 0.5 (all fail) → 1.2 (all success)
                return {"launch_success_rate": rate, "avg_uptime_hours": None, "reputation_multiplier": rep_mult}
            return {"launch_success_rate": None, "avg_uptime_hours": None, "reputation_multiplier": 1.0}

        rep = json.loads(raw)
        successes = rep.get("successes", 0)
        attempts = rep.get("attempts", 1)
        rate = successes / max(attempts, 1)
        avg_uptime = rep.get("avg_uptime_hours")

        # reputation_multiplier: 0.5 (terrible) → 1.0 (neutral) → 1.2 (excellent)
        rep_mult = 0.5 + (rate * 0.7)  # rate=0 → 0.5, rate=1 → 1.2

        # Momentum: recent uptime bonus
        if avg_uptime is not None:
            if avg_uptime > 168:  # 7 days stable
                rep_mult = min(1.2, rep_mult + 0.05)
            elif avg_uptime < 2:  # interrupted within 2 hours recently
                rep_mult = max(0.5, rep_mult - 0.10)

        return {"launch_success_rate": rate, "avg_uptime_hours": avg_uptime, "reputation_multiplier": rep_mult}
    except Exception as e:
        logger.warning(f"[pool_ranking] get_pool_reputation failed: {e}")
        return {"launch_success_rate": None, "avg_uptime_hours": None, "reputation_multiplier": 1.0}


def blacklist_pool_temporary(pool_key: str, ttl_seconds: int = 3600):
    """Temporarily blacklist a pool in Redis."""
    try:
        from backend.core.redis_client import get_redis_client, key_blacklist_global
        r = get_redis_client()
        r.setex(key_blacklist_global(pool_key), ttl_seconds, '1')
        logger.info(f"[pool_ranking] Pool {pool_key} blacklisted for {ttl_seconds}s")
    except Exception as e:
        logger.warning(f"[pool_ranking] blacklist_pool_temporary failed: {e}")


def filter_pools_with_dry_run(pools: list, region: str, session) -> list:
    """
    Filter pools by checking Redis dry-run cache.
    Returns only pools where dry_run:{region}:{az}:{instance_type} cache indicates capacity available.
    Falls back to including pool if cache miss (optimistic).
    """
    try:
        from backend.core.redis_client import get_redis_client
        r = get_redis_client()
        validated = []
        for pool in pools:
            instance_type = getattr(pool, 'instance_type', None) or pool.get('instance_type')
            az = getattr(pool, 'az', None) or pool.get('az')
            cache_key = f"dry_run:{region}:{az}:{instance_type}"
            cached = r.get(cache_key)
            if cached is None:
                # Cache miss — include optimistically
                validated.append(pool)
            elif cached in ('1', b'1', 'true', b'true'):
                validated.append(pool)
            # If cached == '0' or 'false', exclude
        return validated
    except Exception as e:
        logger.warning(f"[pool_ranking] filter_pools_with_dry_run error: {e}")
        return pools

