"""
Backend API Package

FastAPI route modules for all endpoints
"""

from backend.api.auth_routes import router as auth_router
from backend.api.template_routes import router as template_router
from backend.api.audit_routes import router as audit_router

__all__ = [
    "auth_router",
    "template_router",
    "audit_router",
]
