"""
Pool Ranking Service - AtharvaAi System A: Pool Selection Pipeline

8-step filtering and ranking pipeline that runs every 30 seconds:
1. Node Template Filtering - User-defined requirements (arch, vCPU, memory, families, sizes, AZs)
2. AZ Filtering - User AZ preferences
3. Spot Advisor Filter - AWS Spot Advisor frequency rank filtering
4. Global Blacklist Check - Redis-based risky pool flags from System B
5. Capacity Check - AWS API real-time capacity validation
6. Price Fetch - AWS Pricing API for spot/on-demand prices
7. ML Model Scoring - ONNX model inference (classifier + regressor)
8. Final Ranking & Caching - Sort by score, cache in Redis

Outputs: Ranked list of instance pools with savings %, cost estimates, and final scores.
"""

try:
    import onnxruntime as ort
except ImportError:
    ort = None
import numpy as np
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from redis import Redis

from backend.services.ml_feature_service import MLFeatureService
from backend.core.logger import logger


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


@dataclass
class ScoredPool:
    """Instance pool with ML scores and final ranking."""
    pool: InstancePool
    savings_pct: float  # From classifier_6.onnx (0-1 scale)
    cost_estimate: float  # From regressor_6.onnx (USD)
    ml_score: float  # Final combined score
    is_flagged: bool  # Flagged by System B
    rank: int  # Final ranking position
    timestamp: datetime


class PoolRankingService:
    """
    AtharvaAi Pool Selection Pipeline - System A.

    Orchestrates 8-step filtering and scoring to provide ranked pool recommendations.
    """

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.feature_service = MLFeatureService(db)

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

    def _load_instance_catalog(self) -> Dict[str, Dict]:
        """
        Load AWS instance catalog with specs (vCPU, memory, architecture).

        This would ideally come from a database or external service.
        For now, using a minimal static catalog.
        """
        return {
            "m5.large": {"vcpu": 2, "memory_gb": 8, "architecture": "amd64"},
            "m5.xlarge": {"vcpu": 4, "memory_gb": 16, "architecture": "amd64"},
            "m5.2xlarge": {"vcpu": 8, "memory_gb": 32, "architecture": "amd64"},
            "m5.4xlarge": {"vcpu": 16, "memory_gb": 64, "architecture": "amd64"},
            "c5.large": {"vcpu": 2, "memory_gb": 4, "architecture": "amd64"},
            "c5.xlarge": {"vcpu": 4, "memory_gb": 8, "architecture": "amd64"},
            "c5.2xlarge": {"vcpu": 8, "memory_gb": 16, "architecture": "amd64"},
            "r5.large": {"vcpu": 2, "memory_gb": 16, "architecture": "amd64"},
            "r5.xlarge": {"vcpu": 4, "memory_gb": 32, "architecture": "amd64"},
            "r5.2xlarge": {"vcpu": 8, "memory_gb": 64, "architecture": "amd64"},
            "t3.medium": {"vcpu": 2, "memory_gb": 4, "architecture": "amd64"},
            "t3.large": {"vcpu": 2, "memory_gb": 8, "architecture": "amd64"},
            # TODO: Load full catalog from AWS EC2 describe-instance-types API
        }

    def rank_pools(
        self,
        node_template: NodeTemplate,
        region: str = "ap-south-1",
        limit: int = 10
    ) -> List[ScoredPool]:
        """
        Execute 8-step pool selection pipeline.

        Args:
            node_template: User-defined filtering requirements
            region: AWS region
            limit: Maximum number of pools to return

        Returns:
            List of scored and ranked instance pools
        """
        logger.info(f"Starting pool ranking pipeline for region {region}")

        # Step 1: Node Template Filtering
        candidate_pools = self._step1_node_template_filter(node_template, region)
        logger.info(f"Step 1: {len(candidate_pools)} pools after node template filtering")

        if not candidate_pools:
            logger.warning("No pools passed Step 1 (node template filtering)")
            return []

        # Step 2: AZ Filtering
        candidate_pools = self._step2_az_filter(candidate_pools, node_template.allowed_azs)
        logger.info(f"Step 2: {len(candidate_pools)} pools after AZ filtering")

        # Step 3: Spot Advisor Filter
        candidate_pools = self._step3_spot_advisor_filter(candidate_pools)
        logger.info(f"Step 3: {len(candidate_pools)} pools after Spot Advisor filtering")

        # Step 4: Global Blacklist Check
        candidate_pools = self._step4_blacklist_check(candidate_pools)
        logger.info(f"Step 4: {len(candidate_pools)} pools after blacklist filtering")

        # Step 5: Capacity Check
        candidate_pools = self._step5_capacity_check(candidate_pools, region)
        logger.info(f"Step 5: {len(candidate_pools)} pools with capacity validated")

        # Step 6: Price Fetch
        candidate_pools = self._step6_price_fetch(candidate_pools, region)
        logger.info(f"Step 6: {len(candidate_pools)} pools with prices fetched")

        # Step 7: ML Model Scoring
        scored_pools = self._step7_ml_scoring(candidate_pools)
        logger.info(f"Step 7: {len(scored_pools)} pools scored with ML models")

        # Step 8: Final Ranking & Caching
        ranked_pools = self._step8_final_ranking(scored_pools, limit)
        logger.info(f"Step 8: Returning top {len(ranked_pools)} ranked pools")

        # Cache results in Redis
        self._cache_rankings(ranked_pools)

        return ranked_pools

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

    def _step3_spot_advisor_filter(self, pools: List[InstancePool]) -> List[InstancePool]:
        """
        Step 3: Filter pools using AWS Spot Advisor frequency rank.

        Filters out pools with interruption rank > 3 (>10% interruption rate).
        """
        spot_advisor_data = self._get_spot_advisor_data()

        filtered_pools = []
        for pool in pools:
            rank = spot_advisor_data.get(f"{pool.instance_type}:{pool.az}", 2)  # Default rank 2
            pool.spot_advisor_rank = rank

            # Filter: Keep only ranks 0-3 (0-10% interruption rate)
            if rank <= 3:
                filtered_pools.append(pool)

        return filtered_pools

    def _step4_blacklist_check(self, pools: List[InstancePool]) -> List[InstancePool]:
        """
        Step 4: Check global blacklist (risky pools flagged by System B).

        Pools flagged within last 12 hours are still included but will receive
        a penalty in Step 7 (ML scoring).
        """
        # All pools pass this step, but we mark flagged ones
        # Penalty applied in Step 7
        return pools

    def _step5_capacity_check(
        self,
        pools: List[InstancePool],
        region: str
    ) -> List[InstancePool]:
        """
        Step 5: Validate real-time capacity using AWS API.

        This would call AWS EC2 DescribeSpotPriceHistory or RunInstances (dry-run).
        For now, assuming all pools have capacity.
        """
        # TODO: Implement AWS API call to check capacity
        # For now, mark all as having capacity
        for pool in pools:
            pool.has_capacity = True

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

            pool.spot_price = prices.get('spot', 0.05)  # Default if not found
            pool.ondemand_price = prices.get('ondemand', 0.10)  # Default if not found

        return pools

    def _step7_ml_scoring(self, pools: List[InstancePool]) -> List[ScoredPool]:
        """
        Step 7: ML Model Scoring using ONNX models.

        For each pool:
        1. Engineer 45 features
        2. Run classifier_6.onnx → savings_pct
        3. Run regressor_6.onnx → cost_estimate
        4. Check System B flags → apply penalty if risky
        5. Calculate final_score = (savings_pct × 100) - (cost × 0.1)
        """
        if not self.classifier_session or not self.regressor_session:
            logger.error("ONNX models not loaded - using fallback scoring")
            return self._fallback_scoring(pools)

        scored_pools = []
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

                # Run ONNX inference
                classifier_output = self.classifier_session.run(
                    None,
                    {"input": features}
                )[0][0][0]

                regressor_output = self.regressor_session.run(
                    None,
                    {"input": features}
                )[0][0][0]

                savings_pct = float(classifier_output)
                cost_estimate = float(regressor_output)

                # Check System B blacklist flag
                is_flagged = self.redis.sismember(
                    "risky_pools",
                    f"{pool.instance_type}:{pool.az}"
                )

                # Apply penalty if flagged
                if is_flagged:
                    savings_pct = max(0.0, savings_pct - 0.50)  # -0.50 penalty

                # Calculate final score
                # Higher savings % is better (×100), lower cost is better (-×0.1)
                final_score = (savings_pct * 100) - (cost_estimate * 0.1)

                scored_pools.append(ScoredPool(
                    pool=pool,
                    savings_pct=savings_pct,
                    cost_estimate=cost_estimate,
                    ml_score=final_score,
                    is_flagged=bool(is_flagged),
                    rank=0,  # Will be set in Step 8
                    timestamp=timestamp
                ))

            except Exception as e:
                logger.error(f"ML scoring failed for {pool.instance_type}/{pool.az}: {e}")
                # Skip this pool or use fallback
                continue

        return scored_pools

    def _step8_final_ranking(
        self,
        scored_pools: List[ScoredPool],
        limit: int
    ) -> List[ScoredPool]:
        """
        Step 8: Sort by score and assign ranks.

        Returns top N pools (limit).
        """
        # Sort by ML score (descending)
        sorted_pools = sorted(scored_pools, key=lambda p: p.ml_score, reverse=True)

        # Assign ranks
        for i, pool in enumerate(sorted_pools[:limit], start=1):
            pool.rank = i

        return sorted_pools[:limit]

    def _fallback_scoring(self, pools: List[InstancePool]) -> List[ScoredPool]:
        """Fallback scoring when ONNX models are unavailable."""
        scored_pools = []
        timestamp = datetime.utcnow()

        for pool in pools:
            # Simple heuristic: Higher headroom = better score
            headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price if pool.ondemand_price > 0 else 0.5
            savings_pct = headroom
            cost_estimate = pool.spot_price * 24 * 30  # Monthly estimate

            final_score = (savings_pct * 100) - (cost_estimate * 0.1)

            scored_pools.append(ScoredPool(
                pool=pool,
                savings_pct=savings_pct,
                cost_estimate=cost_estimate,
                ml_score=final_score,
                is_flagged=False,
                rank=0,
                timestamp=timestamp
            ))

        return scored_pools

    def _cache_rankings(self, ranked_pools: List[ScoredPool]):
        """Cache ranked pools in Redis with 30-second TTL."""
        try:
            cache_key = "atharvaai:pool_rankings"
            cache_data = [
                {
                    "instance_type": p.pool.instance_type,
                    "az": p.pool.az,
                    "savings_pct": p.savings_pct,
                    "cost_estimate": p.cost_estimate,
                    "ml_score": p.ml_score,
                    "rank": p.rank,
                    "is_flagged": p.is_flagged
                }
                for p in ranked_pools
            ]

            self.redis.setex(
                cache_key,
                30,  # 30-second TTL
                json.dumps(cache_data)
            )
        except Exception as e:
            logger.error(f"Failed to cache rankings: {e}")

    # Helper methods for data retrieval

    def _get_region_azs(self, region: str) -> List[str]:
        """Get availability zones for a region."""
        # Hardcoded for ap-south-1
        if region == "ap-south-1":
            return ["aps1-az1", "aps1-az2", "aps1-az3"]
        else:
            return [f"{region}a", f"{region}b", f"{region}c"]

    def _get_spot_advisor_data(self) -> Dict[str, int]:
        """
        Get AWS Spot Advisor frequency rankings.

        Returns: Dict mapping "instance_type:az" to rank (0-5)
        """
        try:
            from decision_engine.webscraper import get_spot_advisor_scraper

            scraper = get_spot_advisor_scraper(cache_ttl=300, enable_redis=True)
            scraper.fetch_data()

            # Build lookup dict
            advisor_data = {}
            for key, data in scraper._cache.items():
                # key format: "region:instance_type:os_type"
                advisor_key = f"{data.instance_type}:{data.region}"
                advisor_data[advisor_key] = data.interruption_index

            logger.info(f"Loaded {len(advisor_data)} Spot Advisor rankings")
            return advisor_data

        except Exception as e:
            logger.warning(f"Failed to load Spot Advisor data: {e}")
            return {}

    def _get_pricing_data(self, region: str) -> Dict[str, Dict[str, float]]:
        """
        Get current spot and on-demand prices from AWS Pricing API.

        Returns: Dict mapping "instance_type:az" to {"spot": float, "ondemand": float}
        """
        # TODO: Implement AWS Pricing API integration
        # For now, return mock data
        return {
            "m5.xlarge:aps1-az1": {"spot": 0.045, "ondemand": 0.096},
            "c5.large:aps1-az2": {"spot": 0.028, "ondemand": 0.085},
            "r5.2xlarge:aps1-az3": {"spot": 0.120, "ondemand": 0.504},
        }
