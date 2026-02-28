from fastapi import APIRouter
from backend.api.auth_routes import router as auth_router
from backend.api.cluster_routes import router as cluster_router
from backend.api.account_routes import router as account_router
from backend.api.onboarding_routes import router as onboarding_router
from backend.api.health_routes import router as health_router
from backend.api.optimization_routes import router as optimization_router
from backend.api.audit_routes import router as audit_router
from backend.api.policy_routes import router as policy_router
from backend.api.hibernation_routes import router as hibernation_router
from backend.api.metrics_routes import router as metrics_router
from backend.api.admin_routes import router as admin_router
from backend.api.lab_routes import router as lab_router
from backend.api.organization_routes import router as organization_router
from backend.api.billing_routes import router as billing_router
from backend.api.hygiene_routes import router as hygiene_router
from backend.api.team_routes import router as team_router
from backend.api.user_routes import router as user_router
from backend.api.governance_routes import router as governance_router
from backend.api.role_routes import router as role_router
from backend.api.approval_routes import router as approval_router
from backend.api.permission_routes import router as permission_router
from backend.api.ri_routes import router as ri_router
from backend.api.s3_routes import router as s3_router
from backend.api.rds_routes import router as rds_router
from backend.api.transfer_routes import router as transfer_router
from backend.api.agent_routes import router as agent_router
from backend.api.karpenter_routes import router as karpenter_router
from backend.api.node_template_routes import router as node_template_router
from backend.api.optimizer_coordinator_routes import router as optimizer_coordinator_router
from backend.api.pool_rotation_routes import router as pool_rotation_router

# Tag Management Routes
from backend.api.tag_policy_routes import router as tag_policy_router
from backend.api.tag_management_routes import router as tag_management_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(cluster_router)
api_router.include_router(account_router)
api_router.include_router(onboarding_router)
api_router.include_router(health_router)
api_router.include_router(optimization_router)
api_router.include_router(audit_router)
api_router.include_router(policy_router)
api_router.include_router(hibernation_router)
api_router.include_router(metrics_router)
api_router.include_router(admin_router)
api_router.include_router(lab_router)
api_router.include_router(organization_router)
api_router.include_router(billing_router)
api_router.include_router(hygiene_router)
api_router.include_router(governance_router)
api_router.include_router(role_router)
api_router.include_router(team_router)
api_router.include_router(approval_router)
api_router.include_router(permission_router)
api_router.include_router(ri_router)
api_router.include_router(s3_router)
api_router.include_router(rds_router)
api_router.include_router(transfer_router)
api_router.include_router(agent_router)
api_router.include_router(karpenter_router)
api_router.include_router(node_template_router)
api_router.include_router(optimizer_coordinator_router)
api_router.include_router(pool_rotation_router)

# Tag Management
api_router.include_router(tag_policy_router)
api_router.include_router(tag_management_router)
