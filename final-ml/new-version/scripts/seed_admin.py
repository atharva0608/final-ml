#!/usr/bin/env python3
"""
Seed Admin User Script

Manually creates the default admin user if it doesn't exist
"""
import sys
import os
import warnings

# Suppress bcrypt version warning (harmless compatibility warning)
warnings.filterwarnings('ignore', message='.*bcrypt.*')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import SessionLocal, create_tables
from backend.models.user import User, UserRole
from backend.core.crypto import hash_password


def seed_admin():
    """Create default admin user"""
    # Ensure tables exist
    print("📦 Creating database tables if they don't exist...")
    create_tables()
    print("✅ Database tables ready")

    db = SessionLocal()
    try:
        # Check if admin exists
        existing_admin = db.query(User).filter(User.email == "admin@spotoptimizer.com").first()

        if existing_admin:
            print("ℹ️  Admin user already exists: admin@spotoptimizer.com")
            print(f"   Role: {existing_admin.role}")
            print(f"   Created: {existing_admin.created_at}")
            return

        # Create admin user
        print("🔨 Creating default admin user...")
        admin_user = User(
            email="admin@spotoptimizer.com",
            password_hash=hash_password("admin123"),
            role=UserRole.SUPER_ADMIN
        )
        db.add(admin_user)
        db.commit()

        print("✅ Created default admin user successfully!")
        print("")
        print("=" * 50)
        print("Login Credentials:")
        print("  Email:    admin@spotoptimizer.com")
        print("  Password: admin123")
        print("=" * 50)
        print("⚠️  Change password immediately after first login!")

    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
