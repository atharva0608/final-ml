#!/usr/bin/env python3
"""
Seed Demo Data Script

Creates demo users, accounts, and templates for testing and demonstration
"""
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import SessionLocal, create_tables
from backend.models.user import User, UserRole
from backend.models.account import Account, AccountStatus
from backend.models.node_template import NodeTemplate
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
        demo_user = db.query(User).filter(User.email == "demo@client.com").first()
        if not demo_user:
            demo_user = User(
                email="demo@client.com",
                password_hash=hash_password("demo123"),
                role=UserRole.CLIENT,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)
            print(f"  ✅ Created demo client: demo@client.com")
        else:
            print(f"  ℹ️  Demo client already exists")

        # ==================== AWS ACCOUNTS ====================
        print("\n☁️  Creating demo AWS accounts...")

        # Demo AWS Account for client
        demo_account = db.query(Account).filter(
            Account.user_id == demo_user.id,
            Account.aws_account_id == "123456789012"
        ).first()

        if not demo_account:
            demo_account = Account(
                user_id=demo_user.id,
                aws_account_id="123456789012",
                account_name="Demo AWS Account",
                access_key_id="AKIAIOSFODNN7EXAMPLE",  # Demo credentials (not real)
                secret_access_key_encrypted="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                default_region="us-east-1",
                status=AccountStatus.ACTIVE,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(demo_account)
            db.commit()
            db.refresh(demo_account)
            print(f"  ✅ Created demo AWS account for demo@client.com")
        else:
            print(f"  ℹ️  Demo AWS account already exists")

        # ==================== NODE TEMPLATES ====================
        print("\n📋 Creating demo node templates...")

        # Check if demo user already has templates
        existing_templates = db.query(NodeTemplate).filter(
            NodeTemplate.user_id == demo_user.id
        ).count()

        if existing_templates == 0:
            # Default balanced template
            balanced_template = NodeTemplate(
                user_id=demo_user.id,
                name="Balanced - General Purpose",
                description="Balanced configuration with t3, t3a, and m5 families for general workloads",
                instance_families=["t3", "t3a", "m5", "m5a", "m6i"],
                max_interruption_frequency="moderate",
                min_vcpu=2,
                max_vcpu=8,
                min_memory_gib=4,
                max_memory_gib=32,
                architectures=["x86_64"],
                is_default=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(balanced_template)

            # Compute optimized template
            compute_template = NodeTemplate(
                user_id=demo_user.id,
                name="Compute Optimized",
                description="High CPU performance with c5, c5a, c6i families",
                instance_families=["c5", "c5a", "c5n", "c6i", "c6a"],
                max_interruption_frequency="low",
                min_vcpu=4,
                max_vcpu=16,
                min_memory_gib=8,
                max_memory_gib=64,
                architectures=["x86_64"],
                is_default=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(compute_template)

            # Memory optimized template
            memory_template = NodeTemplate(
                user_id=demo_user.id,
                name="Memory Optimized",
                description="High memory capacity with r5, r5a, r6i families",
                instance_families=["r5", "r5a", "r5n", "r6i", "r6a"],
                max_interruption_frequency="moderate",
                min_vcpu=2,
                max_vcpu=16,
                min_memory_gib=16,
                max_memory_gib=128,
                architectures=["x86_64"],
                is_default=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(memory_template)

            db.commit()
            print(f"  ✅ Created 3 demo node templates")
        else:
            print(f"  ℹ️  Demo templates already exist ({existing_templates} templates)")

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
        print("    Email:    demo@client.com")
        print("    Password: demo123")
        print("    Role:     CLIENT")
        print("    Account:  Demo AWS Account (123456789012)")
        print()
        print("=" * 60)
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
