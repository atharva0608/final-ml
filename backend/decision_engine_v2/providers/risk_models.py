"""
Risk Model Implementations

These are the ML "brains" that predict crash probability.
"""

import sys
import pickle
from pathlib import Path
from typing import List, Dict
from ..context import Candidate
from ..interfaces import IRiskModel


class MockRiskModel(IRiskModel):
    """Mock risk model for testing (returns random-ish scores)"""

    @property
    def name(self) -> str:
        return "MockRiskModel"

    def predict(self, candidates: List[Candidate]) -> Dict[str, float]:
        """Return mock predictions"""
        predictions = {}

        for candidate in candidates:
            key = f"{candidate.instance_type}@{candidate.availability_zone}"

            # Mock logic: Larger instances = higher risk
            if 'metal' in candidate.instance_type or '24xlarge' in candidate.instance_type:
                risk = 0.75
            elif '12xlarge' in candidate.instance_type or '16xlarge' in candidate.instance_type:
                risk = 0.60
            elif '4xlarge' in candidate.instance_type or '8xlarge' in candidate.instance_type:
                risk = 0.45
            else:
                risk = 0.30

            # Adjust by spot price (cheaper = more risky in this mock)
            if candidate.spot_price < 0.05:
                risk += 0.15

            predictions[key] = min(risk, 1.0)

        return predictions

    def is_loaded(self) -> bool:
        return True


class AlwaysSafeRiskModel(IRiskModel):
    """Always returns low risk (for testing backend plumbing)"""

    @property
    def name(self) -> str:
        return "AlwaysSafeModel"

    def predict(self, candidates: List[Candidate]) -> Dict[str, float]:
        """Return safe predictions for all candidates"""
        return {
            f"{c.instance_type}@{c.availability_zone}": 0.10
            for c in candidates
        }

    def is_loaded(self) -> bool:
        return True


class FamilyStressRiskModel(IRiskModel):
    """
    Real production model: Family Stress Hardware Contagion Model

    This integrates with the actual LightGBM model trained in
    ml-model/family_stress_model.py
    """

    def __init__(self, model_path: str = None):
        """
        Args:
            model_path: Path to the pickled LightGBM model
                       (e.g., './models/uploaded/family_stress_model.pkl')
        """
        self.model_path = model_path or './models/uploaded/family_stress_model.pkl'
        self.model = None
        self._load_model()

    @property
    def name(self) -> str:
        return "FamilyStressModel"

    def _load_model(self):
        """Load the trained LightGBM model"""
        model_file = Path(self.model_path)

        if not model_file.exists():
            print(f"⚠️  Model file not found: {model_file}")
            print(f"   Run ml-model/family_stress_model.py first to train the model")
            print(f"   Using fallback predictions")
            return

        try:
            with open(model_file, 'rb') as f:
                self.model = pickle.load(f)
            print(f"✓ Loaded FamilyStressModel from {model_file}")
        except Exception as e:
            print(f"⚠️  Failed to load model: {e}")
            print(f"   Using fallback predictions")

    def predict(self, candidates: List[Candidate]) -> Dict[str, float]:
        """Predict crash probability using the FamilyStressModel"""
        if not self.model:
            # Model not loaded - use mock predictions as fallback
            print(f"  ⚠️  Model not loaded, using fallback predictions")
            return MockRiskModel().predict(candidates)

        try:
            import pandas as pd
            import numpy as np

            # Prepare features for the model
            # The model expects these features:
            # ['price_position', 'price_velocity_1h', 'price_volatility_6h',
            #  'price_cv_6h', 'discount_depth', 'family_stress_mean',
            #  'family_stress_max', 'hour_sin', 'hour_cos', 'is_weekend',
            #  'is_business_hours']

            features = []

            for candidate in candidates:
                # For real-time prediction, we need to fetch/calculate these features
                # For now, we'll use simplified estimation based on available data

                # Price position: Assume mid-range (0.5) without historical data
                price_position = 0.5

                # Discount depth: We have this from the candidate
                discount_depth = candidate.discount_depth or 0.5

                # Family stress: Estimate based on spot price volatility
                # High spot price relative to on-demand = high stress
                family_stress_mean = 1 - discount_depth  # Simple estimate
                family_stress_max = family_stress_mean * 1.2  # Assume max is 20% higher

                # Time embeddings: Use current time
                from datetime import datetime
                now = datetime.now()
                hour = now.hour
                hour_sin = np.sin(2 * np.pi * hour / 24)
                hour_cos = np.cos(2 * np.pi * hour / 24)
                is_weekend = 1 if now.weekday() >= 5 else 0
                is_business_hours = 1 if 9 <= hour <= 17 else 0

                # Create feature vector
                feature_vec = {
                    'price_position': price_position,
                    'price_velocity_1h': 0.0,  # Unknown without historical data
                    'price_volatility_6h': 0.01,  # Assume low volatility
                    'price_cv_6h': 0.01,
                    'discount_depth': discount_depth,
                    'family_stress_mean': family_stress_mean,
                    'family_stress_max': family_stress_max,
                    'hour_sin': hour_sin,
                    'hour_cos': hour_cos,
                    'is_weekend': is_weekend,
                    'is_business_hours': is_business_hours,
                }

                features.append(feature_vec)

            # Convert to DataFrame
            df = pd.DataFrame(features)

            # Predict probabilities
            y_pred_proba = self.model.predict_proba(df)[:, 1]  # Probability of class 1 (unstable)

            # Build predictions dict
            predictions = {}
            for candidate, prob in zip(candidates, y_pred_proba):
                key = f"{candidate.instance_type}@{candidate.availability_zone}"
                predictions[key] = float(prob)

            return predictions

        except Exception as e:
            print(f"  ⚠️  Model prediction failed: {e}")
            print(f"     Using fallback predictions")
            return MockRiskModel().predict(candidates)

    def is_loaded(self) -> bool:
        return self.model is not None
