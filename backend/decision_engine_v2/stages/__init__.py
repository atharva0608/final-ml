"""
Pipeline Stages - All stage implementations organized by layer

Layer 1: Input Adapters
Layer 2: Static Intelligence (Filtering)
Layer 3: Risk Engine (ML Models)
Layer 4: Optimization Engine
Layer 5: Reactive Override
Layer 6: Output Adapters
"""

# Layer 1: Input Adapters
from .input_adapters import SingleInstanceInputAdapter, K8sInputAdapter

# Layer 2: Static Intelligence
from .static_intelligence import (
    HardwareCompatibilityFilter,
    SpotAdvisorFilter,
    RightsizingExpander
)

# Layer 3: Risk Engine
from .risk_engine import RiskModelStage

# Layer 4: Optimization
from .optimization import (
    SafetyGateFilter,
    BinPackingCalculator,
    TCOSorter
)

# Layer 5: Reactive Override
from .reactive_override import AWSSignalOverride

# Layer 6: Output Adapters
from .actuators import LogActuator, K8sActuator

__all__ = [
    # Layer 1
    'SingleInstanceInputAdapter',
    'K8sInputAdapter',
    # Layer 2
    'HardwareCompatibilityFilter',
    'SpotAdvisorFilter',
    'RightsizingExpander',
    # Layer 3
    'RiskModelStage',
    # Layer 4
    'SafetyGateFilter',
    'BinPackingCalculator',
    'TCOSorter',
    # Layer 5
    'AWSSignalOverride',
    # Layer 6
    'LogActuator',
    'K8sActuator',
]
