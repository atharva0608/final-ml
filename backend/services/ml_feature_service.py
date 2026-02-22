"""
ML Feature Engineering Service for AtharvaAi Pool Selection

This service generates the 45 features required by ONNX models (classifier_6.onnx, regressor_6.onnx).
Used in System A: Pool Selection Pipeline - Step 7 (ML Model Scoring).

Features:
- 10 temporal features (hour, day, cyclical encodings)
- 3 lag features (1h, 4h, 24h lookback)
- 8 rolling statistics (4h and 24h windows)
- 5 price dynamics (velocity, volatility, headroom, saturation, stability)
- 6 family-time patterns (learned from historical data)
- 3 family stress features (cross-instance contagion)
- 3 event features (holidays, stress events)
- 1 pool risk feature (historical failure rate)
- 6 categorical encodings (family, size, AZ + padding)
"""

import numpy as np
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from backend.models.instance import Instance
from backend.core.logger import logger


class MLFeatureService:
    """Service for engineering ML features for ONNX model inference."""

    def __init__(self, db: Session):
        self.db = db
        self.category_mapping = self._load_category_mapping()
        self.holidays = self._load_holiday_calendar()

    def _load_category_mapping(self) -> Dict[str, List[str]]:
        """Load category mapping for instance family, size, and AZ encoding."""
        try:
            with open('ml_model/model/category_mapping.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load category mapping: {e}")
            # Fallback minimal mapping
            return {
                "instance_family": ["m5", "c5", "r5", "t3", "m6i", "c6i", "r6i"],
                "instance_size": ["nano", "micro", "small", "medium", "large", "xlarge", "2xlarge", "4xlarge"],
                "AZ": ["aps1-az1", "aps1-az2", "aps1-az3"]
            }

    def _load_holiday_calendar(self) -> List[datetime]:
        """Load holiday calendar for event feature engineering."""
        # Static 2026 holidays (can be moved to database or config)
        return [
            datetime(2026, 1, 1),   # New Year
            datetime(2026, 1, 26),  # Republic Day (India)
            datetime(2026, 8, 15),  # Independence Day (India)
            datetime(2026, 10, 2),  # Gandhi Jayanti
            datetime(2026, 12, 25), # Christmas
        ]

    def engineer_features(
        self,
        instance_type: str,
        az: str,
        spot_price: float,
        ondemand_price: float,
        timestamp: Optional[datetime] = None,
        use_minimum: bool = False
    ) -> np.ndarray:
        """
        Generate all 45 features for ONNX model input.

        Args:
            instance_type: AWS instance type (e.g., "m5.xlarge")
            az: Availability zone (e.g., "aps1-az1")
            spot_price: Current spot price
            ondemand_price: On-demand price
            timestamp: Current timestamp (defaults to now)
            use_minimum: If True, use minimum viable features (15 features + padding)

        Returns:
            numpy array of shape (1, 45) with engineered features
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        if use_minimum:
            return self._engineer_minimum_features(
                instance_type, az, spot_price, ondemand_price, timestamp
            )

        features = []

        # 1. Temporal Features (10 features)
        features.extend(self._extract_temporal_features(timestamp))

        # 2. Lag Features (3 features)
        features.extend(self._extract_lag_features(instance_type, az))

        # 3. Rolling Window Features (8 features)
        features.extend(self._extract_rolling_features(instance_type, az))

        # 4. Price Dynamics Features (5 features)
        features.extend(self._extract_price_dynamics(
            instance_type, az, spot_price, ondemand_price
        ))

        # 5. Family-Time Pattern Features (6 features)
        family = instance_type.split('.')[0]
        features.extend(self._extract_family_patterns(family, timestamp))

        # 6. Family Stress Features (3 features)
        features.extend(self._extract_family_stress(family, timestamp))

        # 7. Event Features (3 features)
        features.extend(self._extract_event_features(timestamp))

        # 8. Pool Risk Feature (1 feature)
        features.append(self._get_pool_risk(instance_type, az))

        # 9. Categorical Encodings (6 features)
        features.extend(self._encode_categorical(instance_type, az))

        # Validate total feature count
        if len(features) < 45:
            # Pad with zeros if needed
            features.extend([0.0] * (45 - len(features)))
        elif len(features) > 45:
            # Truncate if too many
            features = features[:45]

        return np.array(features, dtype=np.float32).reshape(1, -1)

    def _extract_temporal_features(self, timestamp: datetime) -> List[float]:
        """Extract 10 temporal features."""
        hour = timestamp.hour
        day_of_week = timestamp.weekday()  # 0 = Monday
        day_of_month = timestamp.day
        month = timestamp.month
        is_weekend = 1.0 if day_of_week >= 5 else 0.0
        is_business_hours = 1.0 if 9 <= hour <= 17 else 0.0

        # Cyclical encodings
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)
        day_sin = np.sin(2 * np.pi * day_of_week / 7)
        day_cos = np.cos(2 * np.pi * day_of_week / 7)

        return [
            float(hour),
            float(day_of_week),
            float(day_of_month),
            float(month),
            is_weekend,
            is_business_hours,
            hour_sin,
            hour_cos,
            day_sin,
            day_cos
        ]

    def _extract_lag_features(self, instance_type: str, az: str) -> List[float]:
        """
        Extract 3 lag features (savings at 1h, 4h, 24h ago).

        Requires: spot_price_history table with 144 data points (24h × 6 points/hour).
        """
        try:
            # Query historical savings (assuming 10-minute intervals)
            # Lag 6 = 1 hour ago, Lag 24 = 4 hours ago, Lag 144 = 24 hours ago
            history = self._get_savings_history(instance_type, az, hours=24)

            if len(history) >= 144:
                return [
                    float(history[-6]),   # 1 hour ago
                    float(history[-24]),  # 4 hours ago
                    float(history[-144])  # 24 hours ago
                ]
            else:
                # Insufficient history - use defaults
                return [0.5, 0.5, 0.5]  # Default 50% savings assumption
        except Exception as e:
            logger.warning(f"Lag features unavailable for {instance_type}/{az}: {e}")
            return [0.5, 0.5, 0.5]

    def _extract_rolling_features(self, instance_type: str, az: str) -> List[float]:
        """
        Extract 8 rolling window features.

        - 4-hour window: mean, std, min, max
        - 24-hour window: mean, std, min, max
        """
        try:
            history = self._get_savings_history(instance_type, az, hours=24)

            if len(history) >= 144:
                recent_24 = history[-24:]   # Last 4 hours
                recent_144 = history[-144:]  # Last 24 hours

                return [
                    float(np.mean(recent_24)),
                    float(np.std(recent_24)),
                    float(np.min(recent_24)),
                    float(np.max(recent_24)),
                    float(np.mean(recent_144)),
                    float(np.std(recent_144)),
                    float(np.min(recent_144)),
                    float(np.max(recent_144))
                ]
            else:
                # Insufficient history - use defaults
                return [0.5, 0.1, 0.3, 0.7, 0.5, 0.15, 0.2, 0.8]
        except Exception as e:
            logger.warning(f"Rolling features unavailable for {instance_type}/{az}: {e}")
            return [0.5, 0.1, 0.3, 0.7, 0.5, 0.15, 0.2, 0.8]

    def _extract_price_dynamics(
        self,
        instance_type: str,
        az: str,
        spot_price: float,
        ondemand_price: float
    ) -> List[float]:
        """Extract 5 price dynamics features."""
        try:
            price_history = self._get_price_history(instance_type, az, hours=6)

            # 1. Price velocity (1-hour change)
            if len(price_history) >= 6:
                price_velocity = (price_history[-1] - price_history[-6]) / price_history[-6]
            else:
                price_velocity = 0.0

            # 2. Price volatility (6-hour std dev)
            if len(price_history) >= 36:
                price_volatility = float(np.std(price_history[-36:]))
            else:
                price_volatility = 0.0

            # 3. Headroom to on-demand
            headroom = (ondemand_price - spot_price) / ondemand_price if ondemand_price > 0 else 0.0

            # 4. Pool saturation (current price relative to range)
            if len(price_history) >= 36:
                min_price = np.min(price_history[-36:])
                pool_saturation = (spot_price - min_price) / (ondemand_price - min_price) if ondemand_price > min_price else 0.0
            else:
                pool_saturation = 0.5  # Default mid-range

            # 5. Consecutive stable hours (price change < 5%)
            stable_hours = self._calculate_consecutive_stable_hours(price_history)

            return [
                float(price_velocity),
                float(price_volatility),
                float(headroom),
                float(pool_saturation),
                float(stable_hours)
            ]
        except Exception as e:
            logger.warning(f"Price dynamics features unavailable: {e}")
            return [0.0, 0.0, 0.5, 0.5, 0.0]

    def _extract_family_patterns(self, family: str, timestamp: datetime) -> List[float]:
        """
        Extract 6 family-time pattern features.

        Requires: family_hour_baselines table with pre-computed statistics.
        """
        try:
            # Query family-hour baselines from database
            # This would be pre-computed from training data
            baselines = self._get_family_baselines(family, timestamp.hour, timestamp.weekday())

            return [
                baselines.get('hour_avg_savings', 0.5),
                baselines.get('hour_std_savings', 0.1),
                baselines.get('dow_avg_savings', 0.5),
                baselines.get('hour_deviation', 0.0),
                baselines.get('hour_zscore', 0.0),
                baselines.get('weekend_avg_savings', 0.5)
            ]
        except Exception as e:
            logger.warning(f"Family patterns unavailable for {family}: {e}")
            return [0.5, 0.1, 0.5, 0.0, 0.0, 0.5]

    def _extract_family_stress(self, family: str, timestamp: datetime) -> List[float]:
        """
        Extract 3 family stress features (cross-instance contagion detection).

        Requires: Real-time monitoring of all instances in the same family.
        """
        try:
            # Query current state of all instances in this family
            stress_metrics = self._calculate_family_stress(family, timestamp)

            return [
                stress_metrics.get('stress_index', 0.0),
                stress_metrics.get('avg_savings', 0.5),
                stress_metrics.get('std_savings', 0.1)
            ]
        except Exception as e:
            logger.warning(f"Family stress features unavailable for {family}: {e}")
            return [0.0, 0.5, 0.1]

    def _extract_event_features(self, timestamp: datetime) -> List[float]:
        """Extract 3 event features (holidays, stress events)."""
        is_holiday = 1.0 if self._is_holiday(timestamp) else 0.0
        is_stress_event = 0.0  # TODO: Integrate with external stress event calendar
        days_to_nearest_event = float(self._days_to_nearest_event(timestamp))

        return [is_holiday, is_stress_event, days_to_nearest_event]

    def _get_pool_risk(self, instance_type: str, az: str) -> float:
        """
        Get historical pool risk score from Spot Advisor data.

        Calculates risk based on interruption frequency ratings.
        """
        try:
            from backend.models.pricing import SpotAdvisorData

            # Query spot advisor data for this instance type
            advisor_data = self.db.query(SpotAdvisorData).filter(
                SpotAdvisorData.instance_type == instance_type
            ).first()

            if advisor_data:
                # Convert interruption index (0-4) to risk percentage
                # 0: <5% = 0.025, 1: 5-10% = 0.075, 2: 10-15% = 0.125, 3: 15-20% = 0.175, 4: >20% = 0.25
                risk_map = {
                    0: 0.025,  # <5% interruption
                    1: 0.075,  # 5-10% interruption
                    2: 0.125,  # 10-15% interruption
                    3: 0.175,  # 15-20% interruption
                    4: 0.250,  # >20% interruption
                }
                return risk_map.get(advisor_data.interruption_index, 0.05)

            # Default to 5% risk if no data available
            return 0.05

        except Exception as e:
            logger.warning(f"Pool risk unavailable for {instance_type}/{az}: {e}")
            return 0.05

    def _encode_categorical(self, instance_type: str, az: str) -> List[float]:
        """Encode categorical features (instance family, size, AZ) + padding."""
        try:
            family, size = instance_type.split('.')

            # Get indices from category mapping
            family_idx = self.category_mapping["instance_family"].index(family) if family in self.category_mapping["instance_family"] else 0
            size_idx = self.category_mapping["instance_size"].index(size) if size in self.category_mapping["instance_size"] else 0
            az_idx = self.category_mapping["AZ"].index(az) if az in self.category_mapping["AZ"] else 0

            return [
                float(family_idx),
                float(size_idx),
                float(az_idx),
                0.0,  # Reserved/padding
                0.0,  # Reserved/padding
                0.0   # Reserved/padding
            ]
        except Exception as e:
            logger.warning(f"Categorical encoding failed for {instance_type}/{az}: {e}")
            return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def _engineer_minimum_features(
        self,
        instance_type: str,
        az: str,
        spot_price: float,
        ondemand_price: float,
        timestamp: datetime
    ) -> np.ndarray:
        """
        Generate minimum viable features (15 real features + 30 zeros).

        Used when historical data is not yet available for a new pool.
        """
        features = []

        # Temporal (10)
        features.extend(self._extract_temporal_features(timestamp))

        # Zeros for lag features (3)
        features.extend([0.0, 0.0, 0.0])

        # Zeros for rolling features (8)
        features.extend([0.0] * 8)

        # Price dynamics (simplified - only headroom, rest zeros)
        headroom = (ondemand_price - spot_price) / ondemand_price if ondemand_price > 0 else 0.0
        features.extend([0.0, 0.0, headroom, 0.0, 0.0])

        # Zeros for family patterns (6)
        features.extend([0.0] * 6)

        # Zeros for family stress (3)
        features.extend([0.0] * 3)

        # Event features (3)
        features.extend(self._extract_event_features(timestamp))

        # Pool risk (1)
        features.append(0.05)

        # Categorical encodings (6)
        features.extend(self._encode_categorical(instance_type, az))

        # Ensure exactly 45 features
        if len(features) < 45:
            features.extend([0.0] * (45 - len(features)))

        return np.array(features, dtype=np.float32).reshape(1, -1)

    # Helper methods for data retrieval

    def _get_savings_history(self, instance_type: str, az: str, hours: int) -> List[float]:
        """Get historical savings values from database."""
        try:
            from backend.models.pricing import SpotPriceHistory
            from datetime import datetime, timedelta

            # Query spot price history for the last N hours
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            prices = self.db.query(SpotPriceHistory).filter(
                SpotPriceHistory.instance_type == instance_type,
                SpotPriceHistory.availability_zone == az,
                SpotPriceHistory.timestamp >= cutoff_time
            ).order_by(SpotPriceHistory.timestamp.desc()).limit(hours * 6).all()  # 10-min intervals = 6 per hour

            if not prices:
                return []

            # Calculate savings as (on_demand - spot) / on_demand
            savings = []
            for price_record in prices:
                if hasattr(price_record, 'ondemand_price') and price_record.ondemand_price:
                    savings_pct = (float(price_record.ondemand_price) - float(price_record.price)) / float(price_record.ondemand_price)
                    savings.append(savings_pct)
                else:
                    # Estimate savings if on-demand price not available (spot is typically 30% of on-demand)
                    savings.append(0.70)

            return savings

        except Exception as e:
            logger.warning(f"Failed to get savings history for {instance_type}/{az}: {e}")
            return []

    def _get_price_history(self, instance_type: str, az: str, hours: int) -> List[float]:
        """Get historical spot prices from database."""
        try:
            from backend.models.pricing import SpotPriceHistory
            from datetime import datetime, timedelta

            # Query spot price history for the last N hours
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            prices = self.db.query(SpotPriceHistory).filter(
                SpotPriceHistory.instance_type == instance_type,
                SpotPriceHistory.availability_zone == az,
                SpotPriceHistory.timestamp >= cutoff_time
            ).order_by(SpotPriceHistory.timestamp.desc()).limit(hours * 6).all()  # 10-min intervals = 6 per hour

            if not prices:
                return []

            # Return spot prices as floats
            return [float(p.price) for p in prices]

        except Exception as e:
            logger.warning(f"Failed to get price history for {instance_type}/{az}: {e}")
            return []

    def _calculate_consecutive_stable_hours(self, price_history: List[float]) -> float:
        """Calculate consecutive hours of price stability (< 5% change)."""
        if len(price_history) < 2:
            return 0.0

        stable_count = 0
        for i in range(len(price_history) - 1, 0, -1):
            change_pct = abs(price_history[i] - price_history[i-1]) / price_history[i-1]
            if change_pct < 0.05:  # Less than 5% change
                stable_count += 1
            else:
                break

        return float(stable_count / 6)  # Convert to hours (assuming 10-min intervals)

    def _get_family_baselines(self, family: str, hour: int, day_of_week: int) -> Dict[str, float]:
        """Get family-hour baseline statistics from database."""
        # TODO: Query family_hour_baselines table
        return {}

    def _calculate_family_stress(self, family: str, timestamp: datetime) -> Dict[str, float]:
        """Calculate real-time family stress metrics."""
        # TODO: Query current instance states for this family
        return {}

    def _is_holiday(self, timestamp: datetime) -> bool:
        """Check if timestamp falls on a holiday."""
        date_only = timestamp.date()
        return any(holiday.date() == date_only for holiday in self.holidays)

    def _days_to_nearest_event(self, timestamp: datetime) -> int:
        """Calculate days to nearest holiday/event."""
        if not self.holidays:
            return 365  # No events in calendar

        date_only = timestamp.date()
        future_holidays = [h for h in self.holidays if h.date() >= date_only]

        if not future_holidays:
            return 365  # No upcoming holidays

        nearest = min(future_holidays, key=lambda h: abs((h.date() - date_only).days))
        return abs((nearest.date() - date_only).days)
