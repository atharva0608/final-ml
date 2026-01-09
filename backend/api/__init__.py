from fastapi import APIRouter
from backend.api.auth_routes import router as auth_router
from backend.api.cluster_routes import router as cluster_router
from backend.api.account_routes import router as account_router
from backend.api.onboarding_routes import router as onboarding_router
# Import new routes
from backend.api.health_routes import router as health_router
from backend.api.optimization_routes import router as optimization_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(cluster_router)
api_router.include_router(account_router)
api_router.include_router(onboarding_router)
# Include new routes
api_router.include_router(health_router)
api_router.include_router(optimization_router)
