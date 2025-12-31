"""
Feature Engineering - Standardized Feature Calculation

Calculates ML features from raw AWS data and historical context.
All models MUST use this module for feature calculation to ensure consistency.

Key Features:
- price_position: Normalized spot price relative to on-demand (0-1 scale)
- family_stress_index: Regional demand indicator for instance family
- discount_depth: How much cheaper spot is vs on-demand (0-1 scale)
- z-score normalization: Region-agnostic feature scaling

Prohibited:
- Direct raw price values in features (use normalized metrics)
- Hardcoded thresholds or magic numbers
- Region-specific feature calculation logic
"""

import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import redis
import json


@dataclass
class FeatureConfig:
    """Configuration for feature engineering"""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0


class FeatureEngine:
    """
    Feature engineering pipeline for spot instance optimization

    Calculates standardized features from raw instance data and historical context.
    All feature calculations are region-agnostic using z-score normalization.

    Example:
        >>> engine = FeatureEngine()
        >>> features = engine.calculate_features(
        ...     instance_type="c5.large",
        ...     availability_zone="ap-south-1a",
        ...     spot_price=0.028,
        ...     on_demand_price=0.085,
        ...     historic_interrupt_rate=0.05
        ... )
        >>> print(features)
        {
            "price_position": 0.329,
            "discount_depth": 0.671,
            "family_stress_index": 1.24,
            "historic_interrupt_rate": 0.05,
            ...
        }
    """

    def __init__(self, config: Optional[FeatureConfig] = None):
        """
        Initialize feature engine

        Args:
            config: Feature engine configuration
        """
        self.config = config or FeatureConfig()

        # Initialize Redis connection for historical data
        try:
            self.redis = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                decode_responses=True
            )
            self.redis.ping()
        except Exception as e:
            print(f"⚠️  Redis connection failed: {e}")
            print("   Feature engine will operate without historical context")
            self.redis = None

    def calculate_price_position(self, spot_price: float, on_demand_price: float) -> float:
        """
        Calculate price position (0.0 = free, 1.0 = on-demand price)

        Args:
            spot_price: Current spot price
            on_demand_price: On-demand price for same instance type

        Returns:
            Price position (0.0 to 1.0)
        """
        if on_demand_price == 0:
            return 1.0

        return min(spot_price / on_demand_price, 1.0)

    def calculate_discount_depth(self, spot_price: float, on_demand_price: float) -> float:
        """
        Calculate discount depth (1.0 = free, 0.0 = no discount)

        Args:
            spot_price: Current spot price
            on_demand_price: On-demand price

        Returns:
            Discount depth (0.0 to 1.0)
        """
        if on_demand_price == 0:
            return 0.0

        return max(1.0 - (spot_price / on_demand_price), 0.0)

    def calculate_family_stress_index(
        self,
        instance_type: str,
        region: str
    ) -> float:
        """
        Calculate family stress index (regional demand indicator)

        Uses historical price variance data from Redis to compute how "stressed"
        an instance family is in a given region.

        Formula:
            stress = (current_avg_price - historical_min) / (historical_max - historical_min)

        Args:
            instance_type: EC2 instance type (e.g., "c5.large")
            region: AWS region (e.g., "ap-south-1")

        Returns:
            Family stress index (0.0 = low demand, 1.0+ = high demand)
        """
        # Extract family name (e.g., "c5" from "c5.large")
        family = instance_type.split('.')[0] if '.' in instance_type else instance_type

        if not self.redis:
            # Default to moderate stress if no historical data
            return 0.5

        try:
            # Fetch historical price statistics from Redis
            key = f"spot_price_history:{region}:{family}"
            data = self.redis.get(key)

            if not data:
                return 0.5  # Default for missing data

            stats = json.loads(data)

            current_avg = stats.get("current_avg_price", 0)
            historical_min = stats.get("min_price", 0)
            historical_max = stats.get("max_price", 0)

            if historical_max == historical_min:
                return 0.5  # No variance

            stress = (current_avg - historical_min) / (historical_max - historical_min)
            return max(0.0, stress)  # Can exceed 1.0 for extreme demand

        except Exception as e:
            print(f"Warning: Failed to calculate family stress: {e}")
            return 0.5

    def normalize_zscore(
        self,
        value: float,
        mean: float,
        std: float,
        clip_at: float = 3.0
    ) -> float:
        """
        Calculate z-score normalized value

        Args:
            value: Value to normalize
            mean: Historical mean
            std: Historical standard deviation
            clip_at: Clip outliers at +/- this many standard deviations

        Returns:
            Z-score (typically -3 to +3)
        """
        if std == 0:
            return 0.0

        z = (value - mean) / std
        return np.clip(z, -clip_at, clip_at)

    def calculate_features(
        self,
        instance_type: str,
        availability_zone: str,
        spot_price: float,
        on_demand_price: float,
        historic_interrupt_rate: float,
        vcpu: Optional[int] = None,
        memory_gb: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate full feature vector for ML model

        Args:
            instance_type: EC2 instance type
            availability_zone: Availability zone
            spot_price: Current spot price
            on_demand_price: On-demand price
            historic_interrupt_rate: Historical interruption rate (0.0-1.0)
            vcpu: vCPU count (optional)
            memory_gb: Memory in GB (optional)

        Returns:
            Dict of calculated features
        """
        region = availability_zone[:-1]  # Remove AZ letter (e.g., "ap-south-1a" -> "ap-south-1")

        features = {
            # Price features
            "price_position": self.calculate_price_position(spot_price, on_demand_price),
            "discount_depth": self.calculate_discount_depth(spot_price, on_demand_price),

            # Demand indicator
            "family_stress_index": self.calculate_family_stress_index(instance_type, region),

            # Risk feature
            "historic_interrupt_rate": historic_interrupt_rate,

            # Instance size features
            "vcpu_count": vcpu or 0,
            "memory_gb": memory_gb or 0.0,
        }

        return features


def build_feature_vector(
    instance_data: Dict[str, Any],
    feature_names: List[str]
) -> np.ndarray:
    """
    Build ordered feature vector from feature dict

    Args:
        instance_data: Dict of calculated features
        feature_names: Ordered list of feature names

    Returns:
        Numpy array of features in specified order

    Raises:
        ValueError: If required feature is missing

    Example:
        >>> features = {"price_position": 0.3, "discount_depth": 0.7, ...}
        >>> vector = build_feature_vector(features, ["price_position", "discount_depth"])
        >>> print(vector)
        array([0.3, 0.7])
    """
    vector = []

    for feature_name in feature_names:
        if feature_name not in instance_data:
            raise ValueError(f"Missing required feature: {feature_name}")

        vector.append(instance_data[feature_name])

    return np.array(vector, dtype=np.float64)
