"""
Backend API Package

FastAPI route modules for all endpoints
"""

from backend.api.auth_routes import router as auth_router
from backend.api.template_routes import router as template_router
from backend.api.audit_routes import router as audit_router
from backend.api.cluster_routes import router as cluster_router
from backend.api.policy_routes import router as policy_router
from backend.api.hibernation_routes import router as hibernation_router
from backend.api.metrics_routes import router as metrics_router
from backend.api.admin_routes import router as admin_router
from backend.api.lab_routes import router as lab_router
from backend.api.onboarding_routes import router as onboarding_router
from backend.api.organization_routes import router as organization_router
from backend.api.settings_routes import router as settings_router

__all__ = [
    "auth_router",
    "template_router",
    "audit_router",
    "cluster_router",
    "policy_router",
    "hibernation_router",
    "metrics_router",
    "admin_router",
    "lab_router",
    "onboarding_router",
    "organization_router",
    "settings_router",
]
