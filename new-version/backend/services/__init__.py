"""
Backend Services Package

Business logic layer for all platform features
"""

from backend.services.auth_service import AuthService, get_auth_service

__all__ = [
    "AuthService",
    "get_auth_service",
]
