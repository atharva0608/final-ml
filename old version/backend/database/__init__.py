"""
Database Package - Production Lab Mode

Contains database models, connection management, and utilities for:
- Multi-tenant AWS account management
- EC2 instance tracking
- ML model registry
- Experiment logging
"""

from .connection import engine, SessionLocal, get_db, seed_demo_data
from .models import (
    Base, User, Account, Instance, MLModel, ExperimentLog,
    Cluster, ClusterStatus, OptimizationPolicy, HibernationSchedule,
    AutoscalerPolicy, AuditLog
)

__all__ = [
    'engine',
    'SessionLocal',
    'get_db',
    'seed_demo_data',
    'Base',
    'User',
    'Account',
    'Instance',
    'MLModel',
    'ExperimentLog',
    'Cluster',
    'ClusterStatus',
    'OptimizationPolicy',
    'HibernationSchedule',
    'AutoscalerPolicy',
    'AuditLog',
]
