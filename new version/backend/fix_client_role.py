#!/usr/bin/env python3
"""
Fix Client User Role Migration Script

This script updates the 'client' test user from role='user' to role='client'
to fix the "Access denied. Client role required" error.

Usage:
    python backend/fix_client_role.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from database.connection import SessionLocal
from database.models import User


def fix_client_user_role():
    """Update client user role from 'user' to 'client'"""
    db = SessionLocal()
    try:
        # Find client user
        client_user = db.query(User).filter(User.username == 'client').first()

        if not client_user:
            print("❌ Client user not found. Please create it first.")
            return False

        if client_user.role == 'client':
            print("✓ Client user already has correct role: 'client'")
            return True

        # Update role
        old_role = client_user.role
        client_user.role = 'client'
        db.commit()

        print(f"✓ Updated client user role: '{old_role}' → 'client'")
        print(f"  Username: {client_user.username}")
        print(f"  Email: {client_user.email}")
        print(f"  Role: {client_user.role}")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("🔧 Fixing client user role...")
    success = fix_client_user_role()
    sys.exit(0 if success else 1)
