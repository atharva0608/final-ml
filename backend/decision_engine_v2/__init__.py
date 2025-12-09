"""
Decision Engine V2 - Modular Pipeline Architecture

This module implements a pluggable, multi-stage decision pipeline for
spot instance management. Each stage is independent and configurable.

Architecture:
    Layer 1: Input Adapters (K8s, SingleInstance)
    Layer 2: Static Intelligence (Filtering)
    Layer 3: Risk Engine (ML Models)
    Layer 4: Optimization Engine (Ranking)
    Layer 5: Reactive Override (AWS Signals)
    Layer 6: Output Adapters (Actuators)
"""

from .context import DecisionContext, Candidate
from .pipeline import DecisionPipeline
from .interfaces import (
    IPipelineStage,
    IInputAdapter,
    IRiskModel,
    IActuator
)

__all__ = [
    'DecisionContext',
    'Candidate',
    'DecisionPipeline',
    'IPipelineStage',
    'IInputAdapter',
    'IRiskModel',
    'IActuator',
]
