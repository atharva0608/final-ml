"""
Base Model Adapter - Standardized ML Model Interface

Defines the interface that all ML models must implement.
Prevents arbitrary code execution and ensures consistent feature handling.

Security Rules:
1. Models MUST only perform inference (no training)
2. Models MUST NOT execute arbitrary Python code
3. Models MUST declare their feature version
4. Feature vectors MUST be validated before inference
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
import numpy as np


class BaseModelAdapter(ABC):
    """
    Base adapter for ML models

    All models loaded by the system MUST implement this interface.

    Example:
        class FamilyStressPredictorV2(BaseModelAdapter):
            def __init__(self, model_path: str):
                self.model = load_model(model_path)

            def get_feature_version(self) -> str:
                return "v2.0"

            def get_expected_features(self) -> List[str]:
                return [
                    "price_position",
                    "family_stress_index",
                    "discount_depth",
                    "historic_interrupt_rate",
                    "vcpu_count",
                    "memory_gb"
                ]

            def preprocess(self, raw_input: Dict[str, Any]) -> np.ndarray:
                # Extract and normalize features
                return np.array([...])

            def predict(self, features: np.ndarray) -> float:
                # Run inference
                return self.model.predict_proba(features)[0][1]
    """

    @abstractmethod
    def get_feature_version(self) -> str:
        """
        Get the feature schema version this model expects

        Returns:
            Feature version string (e.g., "v2.0")
        """
        pass

    @abstractmethod
    def get_expected_features(self) -> List[str]:
        """
        Get list of features this model expects

        Returns:
            List of feature names in expected order
        """
        pass

    @abstractmethod
    def preprocess(self, raw_input: Dict[str, Any]) -> np.ndarray:
        """
        Preprocess raw input into feature vector

        Args:
            raw_input: Raw data dict with keys like:
                - instance_type: str
                - availability_zone: str
                - spot_price: float
                - on_demand_price: float
                - historic_interrupt_rate: float
                - etc.

        Returns:
            Numpy array of features ready for inference

        Raises:
            ValueError: If input is missing required fields
        """
        pass

    @abstractmethod
    def predict(self, features: np.ndarray) -> float:
        """
        Run inference and return crash probability

        Args:
            features: Preprocessed feature vector

        Returns:
            Crash probability (0.0 to 1.0)

        Raises:
            ValueError: If features don't match expected shape
        """
        pass

    def validate_features(self, features: np.ndarray):
        """
        Validate feature vector shape and values

        Args:
            features: Feature vector to validate

        Raises:
            ValueError: If validation fails
        """
        expected_count = len(self.get_expected_features())

        if features.shape[0] != expected_count:
            raise ValueError(
                f"Feature mismatch: expected {expected_count} features, got {features.shape[0]}\n"
                f"Expected: {self.get_expected_features()}"
            )

        # Check for NaN or Inf
        if np.isnan(features).any():
            raise ValueError("Feature vector contains NaN values")

        if np.isinf(features).any():
            raise ValueError("Feature vector contains Inf values")

    def predict_with_validation(self, raw_input: Dict[str, Any]) -> float:
        """
        Full prediction pipeline with validation

        Args:
            raw_input: Raw input dict

        Returns:
            Crash probability

        Raises:
            ValueError: If preprocessing or validation fails
        """
        # Preprocess
        features = self.preprocess(raw_input)

        # Validate
        self.validate_features(features)

        # Predict
        return self.predict(features)
