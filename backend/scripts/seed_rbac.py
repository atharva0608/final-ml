"""
RBAC Seeding Script - Creates Roles and Permissions
Run: docker exec spot-optimizer-backend python -m backend.scripts.seed_rbac
"""
import sys
import os
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Also add /app for Docker
sys.path.insert(0, '/app')

from sqlalchemy.orm import Session
from backend.core.config import get_settings
from backend.models.base import SessionLocal
from backend.models.role import Role
from backend.models.permission import Permission
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.onboarding import OnboardingState

# 1. Define Permissions (The Policies)
PERMISSIONS_LIST = [
    # Consolidated Admin Features
    {"slug": "metrics:view_consolidated", "name": "View Team Aggregated Cost", "module": "Analytics"},
    {"slug": "metrics:view_member_detail", "name": "View Member Breakdown", "module": "Analytics"},
    
    # Compute & Resources
    {"slug": "compute:view", "name": "View Instances", "module": "Compute"},
    {"slug": "compute:terminate", "name": "Terminate Instances", "module": "Compute"},
    {"slug": "compute:terminate:own", "name": "Terminate Own Resources", "module": "Compute"},
    {"slug": "compute:terminate:any", "name": "Terminate Any Team Resource", "module": "Compute"},
    
    # Cloud & Hygiene
    {"slug": "cloud:connect", "name": "Connect AWS Account", "module": "Cloud"},
    {"slug": "hygiene:view_waste", "name": "View Wasted Costs", "module": "Hygiene"},
    
    # Teams & Users
    {"slug": "team:manage", "name": "Manage Team Members", "module": "Team"},
    {"slug": "team:view_all", "name": "View All Teams (Admin)", "module": "Team"},
    
    # Billing
    {"slug": "billing:view", "name": "View Billing", "module": "Billing"},
    {"slug": "billing:manage", "name": "Manage Billing", "module": "Billing"},
]

# 2. Define Roles (The Actors)
ROLES_CONFIG = {
    "ORG_ADMIN": {
        "description": "Organization Owner with full access",
        "permissions": ["*"]  # * means All Permissions
    },
    "TEAM_LEAD": {
        "description": "Team Manager",
        "permissions": [
            "metrics:view_consolidated",
            "metrics:view_member_detail",
            "compute:view",
            "compute:terminate",
            "compute:terminate:any",
            "cloud:connect",
            "hygiene:view_waste",
            "team:manage"
        ]
    },
    "MEMBER": {
        "description": "Standard Contributor",
        "permissions": [
            "compute:view",
            "compute:terminate:own",
            "cloud:connect"
        ]
    }
}


def seed_rbac():
    db = SessionLocal()
    try:
        print("🌱 Seeding Permissions...")
        
        # Insert Permissions
        perm_map = {}
        for p_data in PERMISSIONS_LIST:
            perm = db.query(Permission).filter_by(slug=p_data["slug"]).first()
            if not perm:
                perm = Permission(
                    id=str(uuid.uuid4()),
                    slug=p_data["slug"],
                    name=p_data["name"],
                    module=p_data["module"]
                )
                db.add(perm)
                print(f"   + Created permission: {p_data['slug']}")
            else:
                # Update existing
                perm.name = p_data["name"]
                perm.module = p_data["module"]
            perm_map[p_data["slug"]] = perm
        
        db.commit()
        print(f"   ✅ {len(PERMISSIONS_LIST)} permissions processed")

        print("\n👤 Seeding Roles...")
        # Insert Roles & Attach Permissions
        for role_name, config in ROLES_CONFIG.items():
            role = db.query(Role).filter_by(name=role_name).first()
            if not role:
                role = Role(
                    id=str(uuid.uuid4()),
                    name=role_name,
                    description=config["description"],
                    type="SYSTEM"
                )
                db.add(role)
                print(f"   + Created role: {role_name}")
            else:
                role.description = config["description"]
            
            # Attach Permissions
            if config["permissions"] == ["*"]:
                role.permissions = list(perm_map.values())
            else:
                role.permissions = [perm_map[s] for s in config["permissions"] if s in perm_map]
            
            db.commit()
            print(f"   ✅ {role_name} assigned {len(role.permissions)} permissions")

        print("\n🎉 RBAC Seeding Complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_rbac()
