"""
Multi-Agent System for Spot Optimizer Platform
===============================================

This module implements an 8-agent autonomous architecture for intelligent
spot instance optimization and cluster management.

Agents:
1. GlobalIntelligenceAgent - Region-wide spot pool intelligence
2. DecisionEngineAgent - Policy-driven placement decisions
3. RightsizingAgent - Workload efficiency analysis
4. ClusterExecutionAgent - Kubernetes execution layer
5. EventMonitoringAgent - Termination/rebalance event handling
6. SubstituteManagerAgent - Safety fallback management
7. CapacityValidatorAgent - Batch capacity validation
8. CooldownControllerAgent - Anti-flapping enforcement

Orchestration Order:
1. GlobalIntelligenceAgent (scheduled)
2. CapacityValidator
3. DecisionEngine
4. RightsizingAgent (if needed)
5. CooldownController
6. SubstituteManager (if triggered)
7. ClusterExecutionAgent
8. EventMonitoringAgent (continuous)
"""

from .base import BaseAgent, AgentResponse
from .global_intelligence_agent import GlobalIntelligenceAgent
from .decision_engine_agent import DecisionEngineAgent
from .rightsizing_agent import RightsizingAgent
from .cluster_execution_agent import ClusterExecutionAgent
from .event_monitoring_agent import EventMonitoringAgent
from .substitute_manager_agent import SubstituteManagerAgent
from .capacity_validator_agent import CapacityValidatorAgent
from .cooldown_controller_agent import CooldownControllerAgent
from .orchestrator import AgentOrchestrator

__all__ = [
    'BaseAgent',
    'AgentResponse',
    'GlobalIntelligenceAgent',
    'DecisionEngineAgent',
    'RightsizingAgent',
    'ClusterExecutionAgent',
    'EventMonitoringAgent',
    'SubstituteManagerAgent',
    'CapacityValidatorAgent',
    'CooldownControllerAgent',
    'AgentOrchestrator',
]
