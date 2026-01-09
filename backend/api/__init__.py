from fastapi import APIRouter
from backend.api.auth_routes import router as auth_router
from backend.api.cluster_routes import router as cluster_router
from backend.api.account_routes import router as account_router
from backend.api.onboarding_routes import router as onboarding_router
from backend.api.health_routes import router as health_router
from backend.api.optimization_routes import router as optimization_router
from backend.api.template_routes import router as template_router
from backend.api.audit_routes import router as audit_router
from backend.api.policy_routes import router as policy_router
from backend.api.hibernation_routes import router as hibernation_router
from backend.api.metrics_routes import router as metrics_router
from backend.api.admin_routes import router as admin_router
from backend.api.lab_routes import router as lab_router
from backend.api.organization_routes import router as organization_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(cluster_router)
api_router.include_router(account_router)
api_router.include_router(onboarding_router)
api_router.include_router(health_router)
api_router.include_router(optimization_router)
api_router.include_router(template_router)
api_router.include_router(audit_router)
api_router.include_router(policy_router)
api_router.include_router(hibernation_router)
api_router.include_router(metrics_router)
api_router.include_router(admin_router)
api_router.include_router(lab_router)
api_router.include_router(organization_router)
