"""
Intelligence Modules - Phase 4 Implementation

This package contains the core optimization algorithms and intelligence modules
for the Spot Optimizer platform.

Modules:
- spot_optimizer (MOD-SPOT-01): Instance selection and opportunity detection
- bin_packer (MOD-PACK-01): Cluster fragmentation analysis and consolidation
- rightsizer (MOD-SIZE-01): Resource usage analysis and resize recommendations
- ml_model_server (MOD-AI-01): ML-based Spot interruption predictions
- model_validator (MOD-VAL-01): Template and model contract validation
- risk_tracker (SVC-RISK-GLB): Global risk intelligence ("Hive Mind")
"""

from .spot_optimizer import SpotOptimizationEngine, get_spot_optimizer
from .bin_packer import BinPackingModule, get_bin_packer
from .rightsizer import RightSizingModule, get_rightsizer
from .ml_model_server import MLModelServer, get_ml_model_server
from .model_validator import ModelValidator, get_model_validator
from .risk_tracker import GlobalRiskTracker, get_risk_tracker

__all__ = [
    "SpotOptimizationEngine",
    "BinPackingModule",
    "RightSizingModule",
    "MLModelServer",
    "ModelValidator",
    "GlobalRiskTracker",
    "get_spot_optimizer",
    "get_bin_packer",
    "get_rightsizer",
    "get_ml_model_server",
    "get_model_validator",
    "get_risk_tracker",
]
