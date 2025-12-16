"""
AI Package - ML Inference for Spot Instance Optimization

Contains:
- Base adapters for model inference
- Feature engineering pipeline
- Model loading and validation
"""

from .base_adapter import BaseModelAdapter
from .feature_engine import FeatureEngine, build_feature_vector

__all__ = [
    'BaseModelAdapter',
    'FeatureEngine',
    'build_feature_vector',
]
