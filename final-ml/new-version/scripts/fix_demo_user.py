
import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import settings
from backend.models.base import SessionLocal
from backend.models.user import User, UserRole, OrgRole, AccessLevel
from backend.models.organization import Organization
from backend.models.onboarding import OnboardingState
from backend.core.crypto import hash_password
from datetime import datetime

def fix_demo_user():
    print("🔧 Fixing demo user organization...")
    db = SessionLocal()
    try:
        demo_email = "demo@spotoptimizer.com"
        demo_user = db.query(User).filter(User.email == demo_email).first()
        
        if not demo_user:
            print("❌ Demo user not found! Please run seed_demo_data.py first.")
            return

        print(f"👤 Found demo user: {demo_user.email}")
        
        # Check if organization exists by Name OR Slug
        org_name = "Demo Organization"
        org_slug = "demo-org"
        
        org = db.query(Organization).filter(
            (Organization.name == org_name) | (Organization.slug == org_slug)
        ).first()
        
        if not org:
            print(f"➕ Creating '{org_name}'...")
            org = Organization(
                name=org_name,
                slug=org_slug,
                owner_user_id=demo_user.id,
                status="active"
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"✅ Created organization: {org.id}")
        else:
             print(f"ℹ️  Found organization: {org.id} ({org.name})")
             # Ensure owner is set
             if not org.owner_user_id:
                 org.owner_user_id = demo_user.id
                 db.commit()
                 print("✅ Updated organization owner")

        # Assign user to organization
        if not demo_user.organization_id:
            demo_user.organization_id = org.id
            demo_user.org_role = OrgRole.ORG_ADMIN # Make demo user an admin of their org
            demo_user.access_level = AccessLevel.FULL
            db.commit()
            print(f"✅ Assigned demo user to organization {org.id} as ORG_ADMIN")
        else:
            print(f"ℹ️  Demo user already in organization {demo_user.organization_id}")
            # Ensure role is ORG_ADMIN for full access
            if demo_user.org_role != OrgRole.ORG_ADMIN:
                demo_user.org_role = OrgRole.ORG_ADMIN
                demo_user.access_level = AccessLevel.FULL
                db.commit()
                print("✅ Upgraded demo user to ORG_ADMIN/FULL access")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_demo_user()
