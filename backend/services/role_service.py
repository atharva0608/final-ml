"""
Role Service - Business logic for RBAC management
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.models.role import Role, RoleType
from backend.models.permission import Permission
from backend.models.user import User
from backend.core.exceptions import ResourceNotFoundError, AuthorizationError
import logging

logger = logging.getLogger(__name__)


# Default permissions to seed - SOC2 Compliant List
DEFAULT_PERMISSIONS = [
    # Compute & Resource Management
    {"slug": "compute:view", "module": "Compute", "description": "View read-only lists of EC2 instances, clusters, and resource details"},
    {"slug": "compute:terminate:own", "module": "Compute", "description": "Terminate instances or resources created specifically by the user"},
    {"slug": "compute:terminate:any", "module": "Compute", "description": "Terminate any instance within the user's assigned Team or Organization"},
    {"slug": "storage:delete:own", "module": "Compute", "description": "Delete EBS volumes, Snapshots, or S3 buckets created by the user"},
    {"slug": "storage:delete:any", "module": "Compute", "description": "Delete any storage resource within the assigned Team or Organization"},
    {"slug": "network:modify", "module": "Compute", "description": "Modify Security Groups, release Elastic IPs, or change Route Tables"},
    {"slug": "db:delete", "module": "Compute", "description": "Delete RDS instances or DynamoDB tables (High Risk)"},
    {"slug": "lab:create", "module": "Compute", "description": "Provision new temporary lab environments or experimental clusters"},

    # Cloud Integration & Hygiene
    {"slug": "cloud:connect", "module": "Cloud Integration", "description": "Register a new AWS Account (Access Keys/Role ARN)"},
    {"slug": "cloud:disconnect", "module": "Cloud Integration", "description": "Remove an existing AWS Account connection"},
    {"slug": "hygiene:scan", "module": "Resource Hygiene", "description": "Manually trigger a Resource Hygiene scan"},
    {"slug": "hygiene:view_costs", "module": "Resource Hygiene", "description": "View financial data regarding wasted resources"},
    {"slug": "hygiene:execute", "module": "Resource Hygiene", "description": "Execute cleanup actions (bulk delete) on identified wasted resources"},

    # Governance & Approvals
    {"slug": "approval:approve", "module": "Governance", "description": "Authorize a pending request"},
    {"slug": "approval:reject", "module": "Governance", "description": "Deny a pending request"},
    {"slug": "approval:bypass", "module": "Governance", "description": "Execute post-actions immediately without approval"},
    {"slug": "policy:manage", "module": "Governance", "description": "Create, edit, or disable automated governance rules"},

    # Team & User Administration
    {"slug": "team:create", "module": "Team Management", "description": "Create new Teams within the Organization"},
    {"slug": "team:invite", "module": "Team Management", "description": "Invite new users to the Organization or specific Team"},
    {"slug": "team:remove_member", "module": "Team Management", "description": "Remove a user from a Team or revoking their access"},
    {"slug": "team:promote", "module": "Team Management", "description": "Elevate a user's role (e.g., promoting a Member to Team Lead)"},
    {"slug": "audit:view", "module": "Team Management", "description": "Access the global Audit Logs"},

    # Billing & Financials
    {"slug": "billing:view_spend", "module": "Billing", "description": "View aggregate cost graphs and team spending dashboards"},
    {"slug": "billing:view_invoices", "module": "Billing", "description": "Download official PDF invoices"},
    {"slug": "billing:manage_cc", "module": "Billing", "description": "Add, remove, or update credit card details"},

    # Security & Identity Governance (SOC 2)
    {"slug": "auth:manage_mfa", "module": "Security", "description": "Enforce Multi-Factor Authentication policies"},
    {"slug": "auth:manage_sso", "module": "Security", "description": "Configure or update Single Sign-On (SAML/OIDC)"},
    {"slug": "auth:revoke_session", "module": "Security", "description": "Forcefully invalidate a user's active session"},
    {"slug": "auth:view_login_history", "module": "Security", "description": "View successful and failed login attempts"},
    {"slug": "api_key:manage", "module": "Security", "description": "Create, rotate, or delete Service Account API keys"},
    {"slug": "security:manage_ip", "module": "Security", "description": "Configure IP Whitelisting or CIDR restrictions"},

    # Audit & Compliance (SOC 2)
    {"slug": "audit:export", "module": "Audit", "description": "Export tamper-proof audit logs to external formats"},
    {"slug": "audit:view_sensitive", "module": "Audit", "description": "View highly sensitive audit events"},
    {"slug": "compliance:view_reports", "module": "Audit", "description": "Access generated compliance reports"},
    {"slug": "config:manage_retention", "module": "Audit", "description": "Change data retention periods for logs"},

    # Data Privacy & Confidentiality (SOC 2)
    {"slug": "pii:view", "module": "Privacy", "description": "Unmask Personally Identifiable Information in the UI"},
    {"slug": "pii:export", "module": "Privacy", "description": "Download lists containing customer PII"},
    {"slug": "support:impersonate", "module": "Privacy", "description": "Log in as another user to debug issues"},

    # System Operations (SOC 2)
    {"slug": "system:manage_maintenance", "module": "System", "description": "Enable/Disable Maintenance Mode"},
    {"slug": "system:view_health", "module": "System", "description": "View detailed backend health metrics"},
    {"slug": "alert:manage_destinations", "module": "System", "description": "Configure where critical system alerts are sent"},
]

# Default system roles with their permissions - aligned with WebEngage specification
DEFAULT_SYSTEM_ROLES = {
    "Organization Admin": {
        "description": "Full access to all organization features. Global dashboard view.",
        "permissions": [
            "dashboard:global",
            "user:invite_any", "user:delete",
            "team:create", "team:manage",
            "cloud:connect", "cloud:disconnect",
            "hygiene:view", "hygiene:execute",
            "approval:approve", "approval:override",
            "governance:global", "governance:team",
            "billing:view", "billing:manage",
            "audit:view",
        ]
    },
    "Team Lead": {
        "description": "Manage team, execute cleanups, approve requests. Team dashboard view.",
        "permissions": [
            "dashboard:team",
            "user:invite_team", "user:remove_team",
            "cloud:connect",
            "hygiene:view", "hygiene:execute",
            "approval:approve",
            "governance:team",
        ]
    },
    "Member": {
        "description": "View personal resources, request actions. Personal dashboard view.",
        "permissions": [
            "dashboard:personal",
            "cloud:connect_pending",
            "hygiene:view", "hygiene:request",
        ]
    }
}


class RoleService:
    """Service for managing roles and permissions"""

    def __init__(self, db: Session):
        self.db = db

    def seed_permissions(self) -> int:
        """Seed default permissions if they don't exist"""
        count = 0
        for perm_data in DEFAULT_PERMISSIONS:
            existing = self.db.query(Permission).filter(Permission.slug == perm_data["slug"]).first()
            if not existing:
                perm = Permission(**perm_data)
                self.db.add(perm)
                count += 1
        self.db.commit()
        logger.info(f"Seeded {count} permissions")
        return count

    def seed_system_roles(self) -> int:
        """Seed default system roles if they don't exist"""
        count = 0
        for role_name, role_data in DEFAULT_SYSTEM_ROLES.items():
            existing = self.db.query(Role).filter(
                Role.name == role_name,
                Role.type == RoleType.SYSTEM
            ).first()
            
            if not existing:
                role = Role(
                    name=role_name,
                    type=RoleType.SYSTEM,
                    description=role_data["description"],
                    organization_id=None  # System roles are global
                )
                
                # Add permissions
                for slug in role_data["permissions"]:
                    perm = self.db.query(Permission).filter(Permission.slug == slug).first()
                    if perm:
                        role.permissions.append(perm)
                
                self.db.add(role)
                count += 1
        
        self.db.commit()
        logger.info(f"Seeded {count} system roles")
        return count

    def list_permissions(self) -> List[Permission]:
        """Get all available permissions"""
        return self.db.query(Permission).order_by(Permission.module, Permission.slug).all()

    def list_roles(self, organization_id: Optional[str] = None) -> List[Role]:
        """Get all roles (system + custom for org)"""
        query = self.db.query(Role).filter(
            (Role.type == RoleType.SYSTEM) | (Role.organization_id == organization_id)
        )
        return query.order_by(Role.type, Role.name).all()

    def get_role(self, role_id: str) -> Role:
        """Get a single role by ID"""
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ResourceNotFoundError("Role", role_id)
        return role

    def create_custom_role(self, organization_id: str, name: str, description: str = None, permission_slugs: List[str] = None) -> Role:
        """Create a custom role for an organization"""
        role = Role(
            name=name,
            type=RoleType.CUSTOM,
            description=description,
            organization_id=organization_id
        )
        
        if permission_slugs:
            for slug in permission_slugs:
                perm = self.db.query(Permission).filter(Permission.slug == slug).first()
                if perm:
                    role.permissions.append(perm)
        
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        
        logger.info(f"Created custom role: {name} for org {organization_id}")
        return role

    def update_role(self, role_id: str, name: str = None, description: str = None, permission_slugs: List[str] = None) -> Role:
        """Update a custom role"""
        role = self.get_role(role_id)
        
        if role.type == RoleType.SYSTEM:
            raise AuthorizationError("Cannot modify system roles")
        
        if name:
            role.name = name
        if description is not None:
            role.description = description
        if permission_slugs is not None:
            # Clear existing and add new permissions
            role.permissions.clear()
            for slug in permission_slugs:
                perm = self.db.query(Permission).filter(Permission.slug == slug).first()
                if perm:
                    role.permissions.append(perm)
        
        self.db.commit()
        self.db.refresh(role)
        
        logger.info(f"Updated role: {role.name}")
        return role

    def delete_role(self, role_id: str) -> bool:
        """Delete a custom role"""
        role = self.get_role(role_id)
        
        if role.type == RoleType.SYSTEM:
            raise AuthorizationError("Cannot delete system roles")
        
        # Check if any users are assigned to this role
        user_count = self.db.query(User).filter(User.role_id == role_id).count()
        if user_count > 0:
            raise AuthorizationError(f"Cannot delete role: {user_count} users are still assigned")
        
        self.db.delete(role)
        self.db.commit()
        
        logger.info(f"Deleted role: {role.name}")
        return True

    def assign_role_to_user(self, user_id: str, role_id: str) -> User:
        """Assign a role to a user"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)
        
        role = self.get_role(role_id)
        user.role_id = role.id
        
        self.db.commit()
        self.db.refresh(user)
        
        logger.info(f"Assigned role {role.name} to user {user.email}")
        return user

    def get_user_permissions(self, user: User) -> List[str]:
        """Get all permission slugs for a user"""
        if user.assigned_role:
            return user.assigned_role.permission_slugs
        
        # Fallback to legacy role mapping
        legacy_mapping = {
            "SUPER_ADMIN": [p["slug"] for p in DEFAULT_PERMISSIONS],
            "ORG_ADMIN": [p["slug"] for p in DEFAULT_PERMISSIONS],
            "CLIENT": [p["slug"] for p in DEFAULT_PERMISSIONS],
            "TEAM_LEAD": DEFAULT_SYSTEM_ROLES["Team Lead"]["permissions"],
            "MEMBER": DEFAULT_SYSTEM_ROLES["Member"]["permissions"],
        }
        return legacy_mapping.get(user.role.value, [])

    def user_has_permission(self, user: User, permission: str) -> bool:
        """Check if user has a specific permission"""
        return permission in self.get_user_permissions(user)
