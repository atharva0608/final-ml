"""
Backend Components - Modular Architecture

This package contains the core reusable components that form the backbone
of the AWS Spot Optimizer backend.

Components:
-----------
- data_valve: Data Cleansing and Caching Component (Data Quality Gate)
- calculations: Savings and metrics calculation engine
- command_tracker: Command lifecycle management and priority queuing
- sentinel: Continuous monitoring and fallback trigger system
- decision_engine: ML model loading and I/O contract enforcement
- agent_identity: Agent minting and migration manager

These components enforce clean separation of concerns and provide
scenario-based inline documentation for maintainability.

ARCHITECTURE:
------------
Agent → Sentinel → SEF / Data Valve → Database
          ↓
    Decision Engine → Calculations
          ↓
    Command Tracker → Agent

Each component is standalone with clear interfaces and comprehensive
scenario-based documentation for troubleshooting and future enhancements.
"""

from backend.components.data_valve import data_valve, DataValve, DataValveConfig
from backend.components.calculations import calculation_engine, CalculationEngine, CalculationConfig
from backend.components.command_tracker import command_tracker, CommandTracker, CommandPriority, CommandStatus, CommandType
from backend.components.sentinel import sentinel, SentinelComponent, SentinelConfig, InterruptionSignalType
from backend.components.decision_engine import engine_manager, DecisionEngineManager, DecisionEngineConfig
from backend.components.agent_identity import agent_identity_manager, AgentIdentityManager, AgentIdentityConfig

__all__ = [
    # Data Valve
    'data_valve',
    'DataValve',
    'DataValveConfig',

    # Calculations
    'calculation_engine',
    'CalculationEngine',
    'CalculationConfig',

    # Command Tracker
    'command_tracker',
    'CommandTracker',
    'CommandPriority',
    'CommandStatus',
    'CommandType',

    # Sentinel
    'sentinel',
    'SentinelComponent',
    'SentinelConfig',
    'InterruptionSignalType',

    # Decision Engine
    'engine_manager',
    'DecisionEngineManager',
    'DecisionEngineConfig',

    # Agent Identity
    'agent_identity_manager',
    'AgentIdentityManager',
    'AgentIdentityConfig',
]
