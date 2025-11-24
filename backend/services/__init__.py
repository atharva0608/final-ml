"""
AWS Spot Optimizer - Services Module
=====================================
Centralized exports for all service modules
"""

from backend.services import (
    agent_service,
    pricing_service,
    switch_service,
    replica_service,
    decision_service,
    instance_service,
    client_service,
    notification_service,
    admin_service
)

__all__ = [
    'agent_service',
    'pricing_service',
    'switch_service',
    'replica_service',
    'decision_service',
    'instance_service',
    'client_service',
    'notification_service',
    'admin_service'
]
