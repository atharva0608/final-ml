"""
Enhanced Spot Advisor Scraper - Decision Engine Component

Advanced web scraper for AWS Spot Instance Advisor with:
- Multi-region support
- Real-time data fetching
- Intelligent caching
- Fallback mechanisms
- Data validation
- Historical tracking

Data Source: https://aws.amazon.com/ec2/spot/instance-advisor/
API Endpoint: https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json

Integration: AtharvaAi Pool Selection System (Step 3: Spot Advisor Filter)
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class InterruptionRating(Enum):
    """AWS Spot Advisor interruption frequency ratings."""
    VERY_LOW = 0  # <5%
    LOW = 1       # 5-10%
    MODERATE = 2  # 10-15%
    HIGH = 3      # 15-20%
    VERY_HIGH = 4 # >20%


@dataclass
class SpotAdvisorData:
    """Spot Advisor data for a specific instance type and region."""
    instance_type: str
    region: str
    interruption_index: int  # 0-4
    interruption_frequency: str  # "<5%", "5-10%", etc.
    savings_percentage: int  # 0-100
    os_type: str = "Linux"
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    @property
    def risk_score(self) -> float:
        """Normalized risk score (0.0-1.0)."""
        return self.interruption_index / 4.0

    @property
    def is_safe(self) -> bool:
        """Is this pool safe for production use? (interruption < 10%)"""
        return self.interruption_index <= 1

    @property
    def is_recommended(self) -> bool:
        """Is this pool recommended? (interruption < 10% AND savings >= 50%)"""
        return self.is_safe and self.savings_percentage >= 50


class EnhancedSpotAdvisorScraper:
    """
    Enhanced web scraper for AWS Spot Instance Advisor.

    Features:
    - Real-time data fetching from AWS S3 bucket
    - Multi-region support
    - Intelligent caching (in-memory + optional Redis)
    - Data validation and normalization
    - Fallback to cached data on errors
    - Historical data tracking
    """

    # AWS Spot Advisor public API
    SPOT_ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"

    # Interruption frequency mappings
    FREQUENCY_RATINGS = {
        0: "<5%",
        1: "5-10%",
        2: "10-15%",
        3: "15-20%",
        4: ">20%"
    }

    def __init__(self, cache_ttl: int = 3600, enable_redis: bool = False):
        """
        Initialize the scraper.

        Args:
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
            enable_redis: Enable Redis caching (default: False)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_ttl = cache_ttl
        self.enable_redis = enable_redis

        # In-memory cache
        self._cache: Dict[str, SpotAdvisorData] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._raw_data: Optional[Dict] = None

        # Redis client (optional)
        self.redis_client = None
        if enable_redis:
            try:
                from backend.core.redis_client import get_redis_client
                self.redis_client = get_redis_client()
                self.logger.info("Redis caching enabled")
            except Exception as e:
                self.logger.warning(f"Redis unavailable: {e}")

    def fetch_data(self, force_refresh: bool = False) -> Dict:
        """
        Fetch raw data from AWS Spot Advisor API.

        Args:
            force_refresh: Force refresh even if cache is valid

        Returns:
            Raw JSON data from Spot Advisor API

        Raises:
            requests.RequestException: If fetching fails and no cache available
        """
        # Check cache validity
        if not force_refresh and self._is_cache_valid():
            self.logger.debug("Using cached Spot Advisor data")
            return self._raw_data

        self.logger.info("Fetching fresh Spot Advisor data from AWS")

        try:
            response = requests.get(
                self.SPOT_ADVISOR_URL,
                timeout=30,
                headers={
                    'User-Agent': 'AtharvaAi-SpotOptimizer/1.0'
                }
            )
            response.raise_for_status()

            data = response.json()

            # Validate data structure
            if not self._validate_data_structure(data):
                raise ValueError("Invalid data structure from Spot Advisor API")

            # Update cache
            self._raw_data = data
            self._cache_timestamp = datetime.utcnow()
            self._populate_cache(data)

            self.logger.info(f"Successfully fetched Spot Advisor data at {self._cache_timestamp}")

            return data

        except Exception as e:
            self.logger.error(f"Failed to fetch Spot Advisor data: {e}")

            # Fallback to cached data if available
            if self._raw_data:
                self.logger.warning("Falling back to cached data")
                return self._raw_data
            else:
                raise

    def get_instance_data(
        self,
        instance_type: str,
        region: str,
        os_type: str = "Linux"
    ) -> Optional[SpotAdvisorData]:
        """
        Get Spot Advisor data for a specific instance type and region.

        Args:
            instance_type: EC2 instance type (e.g., "m5.xlarge")
            region: AWS region (e.g., "ap-south-1")
            os_type: Operating system (default: "Linux")

        Returns:
            SpotAdvisorData object or None if not found
        """
        cache_key = f"{region}:{instance_type}:{os_type}"

        # Check in-memory cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check Redis cache
        if self.redis_client:
            redis_key = f"spot_advisor:{cache_key}"
            cached_data = self.redis_client.get(redis_key)
            if cached_data:
                try:
                    data_dict = json.loads(cached_data)
                    return SpotAdvisorData(**data_dict)
                except Exception as e:
                    self.logger.warning(f"Failed to deserialize Redis cache: {e}")

        # Fetch fresh data if cache miss
        try:
            self.fetch_data()
            return self._cache.get(cache_key)
        except Exception as e:
            self.logger.error(f"Failed to get instance data for {instance_type} in {region}: {e}")
            return None

    def get_region_data(
        self,
        region: str,
        os_type: str = "Linux",
        max_interruption: Optional[int] = None,
        min_savings: Optional[int] = None
    ) -> List[SpotAdvisorData]:
        """
        Get all instance types for a specific region with optional filtering.

        Args:
            region: AWS region (e.g., "ap-south-1")
            os_type: Operating system (default: "Linux")
            max_interruption: Maximum interruption index (0-4)
            min_savings: Minimum savings percentage

        Returns:
            List of SpotAdvisorData objects
        """
        # Ensure data is fetched
        self.fetch_data()

        results = []
        for key, data in self._cache.items():
            if data.region == region and data.os_type == os_type:
                # Apply filters
                if max_interruption is not None and data.interruption_index > max_interruption:
                    continue
                if min_savings is not None and data.savings_percentage < min_savings:
                    continue

                results.append(data)

        # Sort by savings (descending)
        results.sort(key=lambda x: x.savings_percentage, reverse=True)

        return results

    def get_recommended_instances(
        self,
        region: str,
        vcpu_min: Optional[int] = None,
        vcpu_max: Optional[int] = None,
        families: Optional[List[str]] = None
    ) -> List[SpotAdvisorData]:
        """
        Get recommended instance types (safe + high savings).

        Args:
            region: AWS region
            vcpu_min: Minimum vCPU count
            vcpu_max: Maximum vCPU count
            families: Allowed instance families (e.g., ["m5", "c5"])

        Returns:
            List of recommended instances sorted by savings
        """
        # Get safe instances (interruption < 10%, savings >= 50%)
        candidates = self.get_region_data(
            region=region,
            max_interruption=1,  # <10%
            min_savings=50
        )

        # Filter by instance family
        if families:
            candidates = [
                c for c in candidates
                if c.instance_type.split('.')[0] in families
            ]

        # TODO: Filter by vCPU (requires instance catalog)
        # For now, just return candidates

        return candidates

    def get_interruption_rank(
        self,
        instance_type: str,
        region: str,
        os_type: str = "Linux"
    ) -> int:
        """
        Get interruption rank for AtharvaAi Step 3 filtering.

        Returns:
            Interruption index (0-4) or 5 if not found
        """
        data = self.get_instance_data(instance_type, region, os_type)
        if data:
            return data.interruption_index
        else:
            # Not found - assume worst case
            return 5

    def get_savings_estimate(
        self,
        instance_type: str,
        region: str,
        os_type: str = "Linux"
    ) -> int:
        """
        Get savings percentage estimate.

        Returns:
            Savings percentage (0-100) or 0 if not found
        """
        data = self.get_instance_data(instance_type, region, os_type)
        if data:
            return data.savings_percentage
        else:
            return 0

    def get_all_regions(self) -> List[str]:
        """Get list of all available regions in Spot Advisor data."""
        self.fetch_data()

        regions = set()
        for data in self._cache.values():
            regions.add(data.region)

        return sorted(list(regions))

    def get_all_instance_types(self, region: Optional[str] = None) -> List[str]:
        """
        Get list of all available instance types.

        Args:
            region: Optional region filter

        Returns:
            List of instance type names
        """
        self.fetch_data()

        instance_types = set()
        for data in self._cache.values():
            if region is None or data.region == region:
                instance_types.add(data.instance_type)

        return sorted(list(instance_types))

    def export_to_dict(self) -> Dict[str, List[Dict]]:
        """
        Export all cached data to dictionary format.

        Returns:
            Dict with region-grouped instance data
        """
        self.fetch_data()

        result = {}
        for data in self._cache.values():
            if data.region not in result:
                result[data.region] = []

            result[data.region].append(asdict(data))

        return result

    def get_statistics(self) -> Dict:
        """
        Get scraper statistics.

        Returns:
            Dict with cache statistics and data counts
        """
        self.fetch_data()

        total_instances = len(self._cache)
        regions = len(self.get_all_regions())

        # Count by interruption rating
        rating_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
        for data in self._cache.values():
            rating_counts[data.interruption_index] += 1

        return {
            "total_instances": total_instances,
            "total_regions": regions,
            "cache_valid": self._is_cache_valid(),
            "cache_age_seconds": self._get_cache_age_seconds(),
            "last_updated": self._cache_timestamp.isoformat() if self._cache_timestamp else None,
            "rating_distribution": {
                "very_low_<5%": rating_counts[0],
                "low_5-10%": rating_counts[1],
                "moderate_10-15%": rating_counts[2],
                "high_15-20%": rating_counts[3],
                "very_high_>20%": rating_counts[4]
            }
        }

    # Private helper methods

    def _is_cache_valid(self) -> bool:
        """Check if in-memory cache is still valid."""
        if self._cache_timestamp is None:
            return False

        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < self.cache_ttl

    def _get_cache_age_seconds(self) -> Optional[int]:
        """Get cache age in seconds."""
        if self._cache_timestamp is None:
            return None

        return int((datetime.utcnow() - self._cache_timestamp).total_seconds())

    def _validate_data_structure(self, data: Dict) -> bool:
        """Validate that data has expected structure."""
        try:
            # Check for "spot_advisor" key
            if "spot_advisor" not in data:
                return False

            spot_data = data["spot_advisor"]

            # Check for at least one OS type
            if len(spot_data) == 0:
                return False

            # Check for at least one region in first OS type
            first_os = next(iter(spot_data.values()))
            if len(first_os) == 0:
                return False

            return True

        except Exception as e:
            self.logger.error(f"Data validation failed: {e}")
            return False

    def _populate_cache(self, data: Dict):
        """Populate in-memory cache from raw data."""
        self._cache.clear()

        spot_data = data.get("spot_advisor", {})

        for os_type, os_data in spot_data.items():
            for region, region_data in os_data.items():
                if region == "ranges":
                    continue  # Skip metadata

                for instance_type, instance_data in region_data.items():
                    interruption_index = instance_data.get("r", 0)
                    savings_percentage = instance_data.get("s", 0)

                    interruption_frequency = self.FREQUENCY_RATINGS.get(
                        interruption_index,
                        "unknown"
                    )

                    advisor_data = SpotAdvisorData(
                        instance_type=instance_type,
                        region=region,
                        interruption_index=interruption_index,
                        interruption_frequency=interruption_frequency,
                        savings_percentage=savings_percentage,
                        os_type=os_type
                    )

                    cache_key = f"{region}:{instance_type}:{os_type}"
                    self._cache[cache_key] = advisor_data

                    # Also cache in Redis if enabled
                    if self.redis_client:
                        redis_key = f"spot_advisor:{cache_key}"
                        self.redis_client.setex(
                            redis_key,
                            self.cache_ttl,
                            json.dumps(asdict(advisor_data))
                        )

        self.logger.info(f"Populated cache with {len(self._cache)} instance/region combinations")


# Singleton instance for easy import
_scraper_instance = None

def get_spot_advisor_scraper(
    cache_ttl: int = 3600,
    enable_redis: bool = False
) -> EnhancedSpotAdvisorScraper:
    """
    Get singleton instance of Spot Advisor scraper.

    Args:
        cache_ttl: Cache TTL in seconds
        enable_redis: Enable Redis caching

    Returns:
        EnhancedSpotAdvisorScraper instance
    """
    global _scraper_instance

    if _scraper_instance is None:
        _scraper_instance = EnhancedSpotAdvisorScraper(
            cache_ttl=cache_ttl,
            enable_redis=enable_redis
        )

    return _scraper_instance


if __name__ == "__main__":
    # Test the scraper
    logging.basicConfig(level=logging.INFO)

    print("=" * 80)
    print("Enhanced Spot Advisor Scraper - Test Run")
    print("=" * 80)

    scraper = EnhancedSpotAdvisorScraper(cache_ttl=3600)

    print("\n1. Fetching data from AWS...")
    scraper.fetch_data()

    print("\n2. Statistics:")
    stats = scraper.get_statistics()
    print(json.dumps(stats, indent=2))

    print("\n3. Available regions:")
    regions = scraper.get_all_regions()
    print(f"Total: {len(regions)}")
    print(regions[:10])

    print("\n4. Test instance lookup (m5.xlarge in us-east-1):")
    data = scraper.get_instance_data("m5.xlarge", "us-east-1")
    if data:
        print(f"  Instance Type: {data.instance_type}")
        print(f"  Region: {data.region}")
        print(f"  Interruption: {data.interruption_frequency} (index: {data.interruption_index})")
        print(f"  Savings: {data.savings_percentage}%")
        print(f"  Risk Score: {data.risk_score:.2f}")
        print(f"  Is Safe: {data.is_safe}")
        print(f"  Is Recommended: {data.is_recommended}")
    else:
        print("  Not found")

    print("\n5. Recommended instances in us-east-1:")
    recommended = scraper.get_recommended_instances("us-east-1", families=["m5", "c5", "r5"])
    print(f"Total: {len(recommended)}")
    for inst in recommended[:5]:
        print(f"  {inst.instance_type}: {inst.savings_percentage}% savings, {inst.interruption_frequency} interruption")

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)
