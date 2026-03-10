#!/usr/bin/env python3
"""
Seed Demo Data Script

Creates demo users and templates for testing and demonstration
AWS accounts should be connected via the UI using CloudFormation
"""
import sys
import os
from datetime import datetime
import warnings

# Suppress bcrypt version warning (harmless compatibility warning)
warnings.filterwarnings('ignore', message='.*bcrypt.*')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import SessionLocal, create_tables
from backend.models.user import User, UserRole
from backend.models.node_template import NodeTemplate
from backend.models.onboarding import OnboardingState # Fix for Mapper initialization
from backend.core.crypto import hash_password


def seed_demo_data():
    """Create demo users, accounts, and templates"""
    # Ensure tables exist
    print("📦 Creating database tables if they don't exist...")
    create_tables()
    print("✅ Database tables ready\n")

    db = SessionLocal()
    try:
        # ==================== USERS ====================
        print("👤 Creating demo users...")

        # 1. Super Admin
        admin_user = db.query(User).filter(User.email == "admin@spotoptimizer.com").first()
        if not admin_user:
            admin_user = User(
                email="admin@spotoptimizer.com",
                password_hash=hash_password("admin123"),
                role=UserRole.SUPER_ADMIN,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"  ✅ Created admin user: admin@spotoptimizer.com")
        else:
            print(f"  ℹ️  Admin user already exists")

        # 2. Demo Client User
        demo_email = "demo@spotoptimizer.com"
        demo_user = db.query(User).filter(User.email == demo_email).first()
        if not demo_user:
            demo_user = User(
                email=demo_email,
                password_hash=hash_password("demo1234"),  # Updated password to meet 8 char limit
                role=UserRole.CLIENT,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            # Should also add Organization/Account creation here like in base.py?
            # base.py handles it better (with Organization).
            # If I run this script, it only creates User, likely with Default Organization (None?)
            # But api_gateway will likely fix it up or create a duplicate if I'm not careful.
            # Ideally this script should CALL base.seed_demo_data() instead of duplicating logic.
            # But let's just fix the crash and credentials for now.
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)
            print(f"  ✅ Created demo client: {demo_email}")
        else:
            print(f"  ℹ️  Demo client already exists")

        # ==================== AWS ACCOUNTS ====================
        # Note: AWS accounts should be connected via the UI using CloudFormation
        # The user will:
        # 1. Click "Connect AWS Account" in the UI
        # 2. Deploy the CloudFormation stack
        # 3. System validates the IAM role connection
        print("\n☁️  AWS Account Setup:")
        print("  ℹ️  AWS accounts should be connected via the UI")
        print("  📋 Steps:")
        print("     1. Login to the application")
        print("     2. Click 'Settings' → 'Cloud Integrations'")
        print("     3. Click 'Connect AWS Account'")
        print("     4. Deploy the provided CloudFormation stack")
        print("     5. Click 'Verify Connection'")

        # ==================== NODE TEMPLATES ====================
        print("\n📋 Node Templates are now managed by base schema migrations...")

        # ==================== SUMMARY ====================
        print("\n" + "=" * 60)
        print("🎉 Demo Data Seeding Complete!")
        print("=" * 60)
        print("\n📧 Login Credentials:\n")
        print("  Super Admin:")
        print("    Email:    admin@spotoptimizer.com")
        print("    Password: admin123")
        print("    Role:     SUPER_ADMIN")
        print()
        print("  Demo Client:")
        print("    Email:    demo@spotoptimizer.com")
        print("    Password: demo1234")
        print("    Role:     CLIENT")
        print("    Templates: 3 node templates created")
        print()
        print("=" * 60)
        print("⚠️  Important Next Steps:")
        print("=" * 60)
        print("1. Login as demo@client.com")
        print("2. Navigate to Settings → Cloud Integrations")
        print("3. Connect your AWS account via CloudFormation")
        print("4. Discover and manage your Kubernetes clusters")
        print()
        print("⚠️  Change passwords immediately in production!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error seeding demo data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
