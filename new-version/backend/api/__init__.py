"""
Backend API Package

FastAPI route modules for all endpoints
"""

from backend.api.auth_routes import router as auth_router

__all__ = [
    "auth_router",
]
