"""
Pool Ranking Service - AtharvaAi System A: Pool Selection Pipeline

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
GLOBAL_CACHE_LIMIT = 500      # Top 500 safest pools cached per region (no template filter)


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
    AtharvaAi Pool Selection Pipeline - System A.

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
            logger.info("ONNX models loaded successfully")
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
            logger.info(f"Risk config loaded: threshold={threshold}")
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
        limit: int = 10
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

        Returns:
            List of scored and ranked instance pools
        """
        logger.info(f"Starting two-tier pool ranking for region={region}, limit={limit}")

        # ── Tier 1: Get/compute global top-N (cached in Redis) ────────────────
        global_pools = self._get_or_compute_global_rankings(region, GLOBAL_CACHE_LIMIT)

        if not global_pools:
            logger.warning(f"Global pipeline returned no pools for region {region}")
            return []

        # ── Tier 2: Apply client template + per-client blacklist filter ────────
        filtered_pools = self._apply_client_filters(global_pools, node_template, region, limit)

        if not filtered_pools:
            logger.warning("No pools matched client template filters — global cache may need expansion")
            return []

        # ── Step 9: Post-score capacity check on client-filtered results ───────
        ranked_pools = self._step9_post_score_capacity_check(filtered_pools, region)
        logger.info(f"Two-tier pipeline complete: returning {len(ranked_pools)} pools")

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

        Tiered Spot Advisor filtering (3 passes, stops when global_limit met):
          Pass 0: max_rank=0 (<5% interruption only — safest pools)
          Pass 1: max_rank=1 (≤10% interruption — <5% and 5-10%)
          Pass 2: max_rank=2 (≤15% interruption — includes 10-15% overflow)
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
        # Step 4: Hard-reject repeat blacklist offenders (failure_count >= 3)
        candidate_pools = self._step4_blacklist_check(candidate_pools, region)

        # Step 6: Fetch spot + on-demand prices
        candidate_pools = self._step6_price_fetch(candidate_pools, region)

        # Step 7: ML scoring
        scored_pools = self._step7_ml_scoring(candidate_pools, region)

        # Intelligence risk cutoff
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
                pools = [self._pool_from_dict(d) for d in pool_dicts]
                logger.info(f"Global cache HIT for {region}: {len(pools)} pools")
                return pools
        except Exception as e:
            logger.warning(f"Global cache read failed for {region}: {e}")

        # Cache miss — run full global pipeline
        logger.info(f"Global cache MISS for {region} — running full pipeline")
        global_pools = self._run_global_pipeline(region, global_limit)

        try:
            cache_data = [self._pool_to_dict(p) for p in global_pools]
            self.redis.setex(cache_key, GLOBAL_CACHE_TTL, json.dumps(cache_data))
            logger.info(
                f"Global cache STORED for {region}: {len(global_pools)} pools "
                f"(TTL={GLOBAL_CACHE_TTL}s)"
            )
        except Exception as e:
            logger.error(f"Global cache write failed for {region}: {e}")

        return global_pools

    def _apply_client_filters(
        self,
        global_pools: List["ScoredPool"],
        template: NodeTemplate,
        region: str,
        limit: int,
    ) -> List["ScoredPool"]:
        """
        Tier 2: Apply node-template + per-client blacklist filters to the cached
        global pool list.  Runs entirely in-memory — no DB or AWS calls.

        Filters applied (in order):
          • Architecture
          • vCPU range
          • Memory range
          • Allowed families (template.allowed_families)
          • Allowed sizes   (template.allowed_sizes)
          • Allowed AZs     (template.allowed_azs)
          • Excluded instance types
          • Hard blacklist: failure_count >= 3 (client-side defense)

        Re-ranks filtered pools 1 → N.
        """
        blacklist_failures_prefix = "blacklist_failures:"
        filtered: List["ScoredPool"] = []

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

            # vCPU range
            if not (template.vcpu_range[0] <= p.vcpu <= template.vcpu_range[1]):
                continue

            # Memory range
            if not (template.memory_range[0] <= p.memory_gb <= template.memory_range[1]):
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

            filtered.append(pool)
            if len(filtered) >= limit:
                break

        # Re-rank 1 → N relative to client view
        for i, pool in enumerate(filtered, start=1):
            pool.rank = i

        logger.info(
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
                      Default 1 (≤10%).  Called with 2 (≤15%) for overflow.
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
                    rank = 1  # Conservative fallback
                    fallback_count += 1

            pool.spot_advisor_rank = rank

            if rank <= max_rank:
                filtered_pools.append(pool)

        if fallback_count > 0:
            logger.warning(
                f"[SPOT-ADVISOR] {fallback_count}/{len(pools)} pools used "
                f"fallback rank=1 (no Spot Advisor data found). "
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
                failure_count = int(self.redis.get(f"blacklist_failures:{pool_key}") or 1)

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
        ml_fail_count = int(self.redis.get("atharvaai:ml_fail_count") or 0)
        if ml_fail_count > 5:
            self.redis.set("atharvaai:ml_degraded", "true", ex=600)  # 10-minute flag
            logger.error("ML circuit breaker OPEN — using fallback scoring (>5 failures in 10 min)")
            return self._fallback_scoring(pools)

        if not self.classifier_session or not self.regressor_session:
            logger.error("ONNX models not loaded - using fallback scoring")
            # Increment circuit breaker counter
            pipe = self.redis.pipeline()
            pipe.incr("atharvaai:ml_fail_count")
            pipe.expire("atharvaai:ml_fail_count", 600)  # 10-minute window
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
            logger.info(f"Loaded {len(sa_savings_map)} SA savings% for scoring differentiation")
        except Exception as _e:
            logger.warning(f"Could not load SA savings data for scoring: {_e}")

        scored_pools = []
        rejected_risky = 0
        timestamp = datetime.utcnow()

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

                # ── Differentiated risk: weighted blend of ONNX + Spot Advisor ─
                # 50/50 blend gives all 4 SA rank buckets distinct, meaningful risk scores
                # while keeping sa_rank=2 (10-15% interruption) pools available:
                #   sa_rank=0 (< 5%): risk ≈ 0.14   sa_rank=2 (10-15%): risk ≈ 0.34
                #   sa_rank=1 (5-10%): risk ≈ 0.24  sa_rank=3 (15-20%): risk ≈ 0.44
                sa_risk = pool.spot_advisor_rank / 5.0  # 0.0 (safest) → 0.8 (riskiest)
                risk_probability = min(1.0, 0.5 * risk_probability + 0.5 * sa_risk)

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

                # ── Expected Value scoring (Decision Engine v3) ──
                from backend.core.scoring import compute_expected_value
                final_score = compute_expected_value(effective_savings, risk_probability)

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
                pipe.incr("atharvaai:ml_fail_count")
                pipe.expire("atharvaai:ml_fail_count", 600)
                pipe.execute()
                continue

        # Clear degraded flag on successful pipeline completion
        if scored_pools:
            self.redis.delete("atharvaai:ml_degraded")

        logger.info(
            f"Step 7 complete: {len(scored_pools)} safe pools, "
            f"{rejected_risky} rejected (risk > {self.risk_threshold})"
        )
        return scored_pools

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
            for p in scored_pools[:TARGET_VALID]:
                p.capacity_status = "unvalidated"
                p.capacity_validated_at = None
            if self.redis:
                self.redis.incr("spot:metrics:dryrun_starvation_ratio")
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

        logger.info(f"DryRun validated {len(validated)}/{TARGET_VALID} pools (budget: {MAX_DRYRUN_PER_HOUR - current_count - len(validated)}/{MAX_DRYRUN_PER_HOUR} remaining)")

        # FALLBACK: If no pools validated (e.g., all DryRun failed due to missing params),
        # return top pools anyway marked as "unvalidated" so UI can still show rankings
        if len(validated) == 0 and len(scored_pools) > 0:
            logger.warning(f"No pools validated via DryRun - returning top {TARGET_VALID} as unvalidated")
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
            cache_key = "atharvaai:pool_rankings"
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
        Get current spot and on-demand prices from database and AWS Pricing API.

        Returns: Dict mapping "instance_type:az" to {"spot": float, "ondemand": float}
        """
        try:
            from backend.models.pricing import SpotPriceHistory, OnDemandPricing
            from backend.services.resource_pricing_service import ResourcePricingService
            from datetime import datetime, timedelta

            pricing_data = {}

            # Get recent spot prices from database (within last hour)
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            spot_prices = self.db.query(SpotPriceHistory).filter(
                SpotPriceHistory.region == region,
                SpotPriceHistory.timestamp >= one_hour_ago
            ).all()

            # Build spot price lookup
            spot_lookup = {}
            for record in spot_prices:
                key = f"{record.instance_type}:{record.availability_zone}"
                spot_lookup[key] = float(record.price)

            # Get on-demand prices
            pricing_service = ResourcePricingService(self.db)
            ondemand_prices = self.db.query(OnDemandPricing).filter(
                OnDemandPricing.region == region
            ).all()

            # Build combined pricing data
            for spot_record in spot_prices:
                key = f"{spot_record.instance_type}:{spot_record.availability_zone}"

                # Get on-demand price from database or API
                ondemand = None
                for od_record in ondemand_prices:
                    if od_record.instance_type == spot_record.instance_type:
                        ondemand = float(od_record.price)
                        break

                # Fallback chain: ResourcePricingService API → hardcoded table → spot * 3.0
                if ondemand is None:
                    try:
                        ondemand_cost = pricing_service.calculate_instance_cost(
                            spot_record.instance_type, region, hours=1
                        )
                        ondemand = float(ondemand_cost)
                    except Exception as e:
                        logger.warning(f"Failed to get on-demand price for {spot_record.instance_type}: {e}")
                        # Use hardcoded accurate OD prices instead of spot * 3.0 (which
                        # gives constant 67% headroom for ALL instance types).
                        ondemand = self._ONDEMAND_FALLBACK.get(
                            spot_record.instance_type,
                            spot_lookup.get(key, 0.0) * 3.0  # Last resort
                        )

                pricing_data[key] = {
                    "spot": spot_lookup.get(key, 0.0),
                    "ondemand": ondemand
                }

            logger.info(f"Loaded pricing data for {len(pricing_data)} instance/AZ combinations")
            return pricing_data

        except Exception as e:
            logger.error(f"Failed to load pricing data: {e}")
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            # Fallback to empty dict (will use fallback pricing in ML features)
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
        vcpu_min = max(1, vcpu - 1)
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

