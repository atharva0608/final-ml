"""
Backend Components - Modular Architecture

This package contains the core reusable components that form the backbone
of the AWS Spot Optimizer backend.

Components:
-----------
- data_valve: Data Cleansing and Caching Component (Data Quality Gate)
- calculations: Savings and metrics calculation engine
- command_tracker: Command lifecycle management and priority queuing

These components enforce clean separation of concerns and provide
scenario-based inline documentation for maintainability.
"""

from backend.components.data_valve import data_valve, DataValve, DataValveConfig
from backend.components.calculations import calculation_engine, CalculationEngine, CalculationConfig
from backend.components.command_tracker import command_tracker, CommandTracker, CommandPriority, CommandStatus, CommandType

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
]
