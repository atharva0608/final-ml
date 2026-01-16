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
# Default permissions to seed - SOC2 Compliant List
DEFAULT_PERMISSIONS = [
    # Compute & Resource Management
    {"slug": "compute:view", "name": "View Compute Resources", "module": "Compute", "description": "View read-only lists of EC2 instances, clusters, and resource details"},
    {"slug": "compute:terminate:own", "name": "Terminate Own Instances", "module": "Compute", "description": "Terminate instances or resources created specifically by the user"},
    {"slug": "compute:terminate:any", "name": "Terminate Any Instance", "module": "Compute", "description": "Terminate any instance within the user's assigned Team or Organization"},
    {"slug": "storage:delete:own", "name": "Delete Own Storage", "module": "Compute", "description": "Delete EBS volumes, Snapshots, or S3 buckets created by the user"},
    {"slug": "storage:delete:any", "name": "Delete Any Storage", "module": "Compute", "description": "Delete any storage resource within the assigned Team or Organization"},
    {"slug": "network:modify", "name": "Modify Network Settings", "module": "Compute", "description": "Modify Security Groups, release Elastic IPs, or change Route Tables"},
    {"slug": "db:delete", "name": "Delete Databases", "module": "Compute", "description": "Delete RDS instances or DynamoDB tables (High Risk)"},
    {"slug": "lab:create", "name": "Create Lab Environment", "module": "Compute", "description": "Provision new temporary lab environments or experimental clusters"},

    # Cloud Integration & Hygiene
    {"slug": "cloud:connect", "name": "Connect Cloud Account", "module": "Cloud Integration", "description": "Register a new AWS Account (Access Keys/Role ARN)"},
    {"slug": "cloud:disconnect", "name": "Disconnect Cloud Account", "module": "Cloud Integration", "description": "Remove an existing AWS Account connection"},
    {"slug": "hygiene:scan", "name": "Run Hygiene Scan", "module": "Resource Hygiene", "description": "Manually trigger a Resource Hygiene scan"},
    {"slug": "hygiene:view_costs", "name": "View Wasted Costs", "module": "Resource Hygiene", "description": "View financial data regarding wasted resources"},
    {"slug": "hygiene:execute", "name": "Execute Cleanup", "module": "Resource Hygiene", "description": "Execute cleanup actions (bulk delete) on identified wasted resources"},

    # Governance & Approvals
    {"slug": "approval:approve", "name": "Approve Requests", "module": "Governance", "description": "Authorize a pending request"},
    {"slug": "approval:reject", "name": "Reject Requests", "module": "Governance", "description": "Deny a pending request"},
    {"slug": "approval:bypass", "name": "Bypass Approval", "module": "Governance", "description": "Execute post-actions immediately without approval"},
    {"slug": "policy:manage", "name": "Manage Policies", "module": "Governance", "description": "Create, edit, or disable automated governance rules"},

    # Team & User Administration
    {"slug": "team:create", "name": "Create Teams", "module": "Team Management", "description": "Create new Teams within the Organization"},
    {"slug": "team:invite", "name": "Invite Users", "module": "Team Management", "description": "Invite new users to the Organization or specific Team"},
    {"slug": "team:remove_member", "name": "Remove Members", "module": "Team Management", "description": "Remove a user from a Team or revoking their access"},
    {"slug": "team:promote", "name": "Promote Members", "module": "Team Management", "description": "Elevate a user's role (e.g., promoting a Member to Team Lead)"},
    {"slug": "audit:view", "name": "View Audit Logs", "module": "Team Management", "description": "Access the global Audit Logs"},

    # Billing & Financials
    {"slug": "billing:view_spend", "name": "View Spending", "module": "Billing", "description": "View aggregate cost graphs and team spending dashboards"},
    {"slug": "billing:view_invoices", "name": "View Invoices", "module": "Billing", "description": "Download official PDF invoices"},
    {"slug": "billing:manage_cc", "name": "Manage Payment Methods", "module": "Billing", "description": "Add, remove, or update credit card details"},

    # Security & Identity Governance (SOC 2)
    {"slug": "auth:manage_mfa", "name": "Manage MFA Policies", "module": "Security", "description": "Enforce Multi-Factor Authentication policies"},
    {"slug": "auth:manage_sso", "name": "Manage SSO", "module": "Security", "description": "Configure or update Single Sign-On (SAML/OIDC)"},
    {"slug": "auth:revoke_session", "name": "Revoke Sessions", "module": "Security", "description": "Forcefully invalidate a user's active session"},
    {"slug": "auth:view_login_history", "name": "View Login History", "module": "Security", "description": "View successful and failed login attempts"},
    {"slug": "api_key:manage", "name": "Manage API Keys", "module": "Security", "description": "Create, rotate, or delete Service Account API keys"},
    {"slug": "security:manage_ip", "name": "Manage IP Whitelist", "module": "Security", "description": "Configure IP Whitelisting or CIDR restrictions"},

    # Audit & Compliance (SOC 2)
    {"slug": "audit:export", "name": "Export Audit Logs", "module": "Audit", "description": "Export tamper-proof audit logs to external formats"},
    {"slug": "audit:view_sensitive", "name": "View Sensitive Events", "module": "Audit", "description": "View highly sensitive audit events"},
    {"slug": "compliance:view_reports", "name": "View Compliance Reports", "module": "Audit", "description": "Access generated compliance reports"},
    {"slug": "config:manage_retention", "name": "Manage Log Retention", "module": "Audit", "description": "Change data retention periods for logs"},

    # Data Privacy & Confidentiality (SOC 2)
    {"slug": "pii:view", "name": "View PII", "module": "Privacy", "description": "Unmask Personally Identifiable Information in the UI"},
    {"slug": "pii:export", "name": "Export PII", "module": "Privacy", "description": "Download lists containing customer PII"},
    {"slug": "support:impersonate", "name": "Impersonate Users", "module": "Privacy", "description": "Log in as another user to debug issues"},

    # System Operations (SOC 2)
    {"slug": "system:manage_maintenance", "name": "Manage Maintenance", "module": "System", "description": "Enable/Disable Maintenance Mode"},
    {"slug": "system:view_health", "name": "View System Health", "module": "System", "description": "View detailed backend health metrics"},
    {"slug": "alert:manage_destinations", "name": "Manage Alert Destinations", "module": "System", "description": "Configure where critical system alerts are sent"},
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
        """
        Get all permission slugs for a user.
        Merges permissions from:
        1. Assigned Role
        2. Custom/Direct Permissions
        """
        permissions = set()

        # 1. Role Permissions
        if user.assigned_role:
            permissions.update(user.assigned_role.permission_slugs)
        
        # 2. Custom/Direct Permissions
        # Note: custom_permissions relationship must be loaded
        if user.custom_permissions:
            permissions.update([p.slug for p in user.custom_permissions])
            
        # If we found permissions via DB, return them
        if permissions:
            return list(permissions)
        
        # 3. Fallback to legacy role mapping (if no DB role/perms found)
        # This ensures backward compatibility during migration
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

    def update_user_permissions(self, user_id: str, permission_slugs: List[str]) -> User:
        """
        Update direct/custom permissions for a user.
        Replaces existing custom permissions with the new list.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)

        # Clear existing custom permissions
        user.custom_permissions.clear()

        # Add new permissions
        for slug in permission_slugs:
            perm = self.db.query(Permission).filter(Permission.slug == slug).first()
            if perm:
                user.custom_permissions.append(perm)
        
        self.db.commit()
        self.db.refresh(user)
        logger.info(f"Updated custom permissions for user {user.email}: {len(permission_slugs)} permissions")
        return user
