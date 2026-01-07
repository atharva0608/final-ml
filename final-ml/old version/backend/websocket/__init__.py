"""
WebSocket Package

Real-time communication for log streaming and status updates.
"""

from .manager import manager, ConnectionManager

__all__ = ['manager', 'ConnectionManager']
