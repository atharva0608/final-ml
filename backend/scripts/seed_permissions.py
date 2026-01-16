"""
Seed Permissions Script
Populates the database with the defined granular permissions.
"""
import sys
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.config import get_settings
from backend.models.permission import Permission
from backend.models.base import Base
# Import other models to ensure relationships are resolved
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.role import Role
from backend.models.onboarding import OnboardingState


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Full list of permissions with Names
PERMISSIONS_LIST = [
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

def seed_permissions():
    """Seed the database with permissions"""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        logger.info("Checking permissions...")
        
        # Create permissions if they don't exist
        created_count = 0
        updated_count = 0
        
        for perm_data in PERMISSIONS_LIST:
            existing = db.query(Permission).filter(Permission.slug == perm_data["slug"]).first()
            
            if not existing:
                perm = Permission(**perm_data)
                db.add(perm)
                created_count += 1
            else:
                # Update name/description/module if changed
                if (existing.name != perm_data["name"] or 
                    existing.description != perm_data["description"] or
                    existing.module != perm_data["module"]):
                    existing.name = perm_data["name"]
                    existing.description = perm_data["description"]
                    existing.module = perm_data["module"]
                    updated_count += 1
        
        db.commit()
        logger.info(f"Summary: Created {created_count}, Updated {updated_count} permissions.")
        
    except Exception as e:
        logger.error(f"Error seeding permissions: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_permissions()
