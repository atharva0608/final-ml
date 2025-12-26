#!/usr/bin/env python3
"""
Demo Data Injection Script

Injects realistic demo data into the database for UI testing and development.
Creates one demo client account with instances, cost data, and recommendations.

Usage:
    python scripts/inject_demo_data.py

Requires:
    - Database must be initialized (alembic migrations run)
    - Backend dependencies installed

Creates:
    - 1 demo user (demo@example.com / demo123)
    - 1 AWS account (connected and active)
    - 15 EC2 instances with varied configurations
    - 30 days of cost optimization data
    - Realistic CloudWatch metrics
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy.orm import Session
from passlib.context import CryptContext
import uuid

# Import models
from database.connection import get_db_session
from database.models import User, Account, Instance, ExperimentLog

# Password hasher
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_demo_user(db: Session):
    """Create demo user account"""
    print("Creating demo user...")

    # Check if demo user already exists
    existing_user = db.query(User).filter(User.username == "demo@example.com").first()
    if existing_user:
        print("  ✓ Demo user already exists")
        return existing_user

    user = User(
        id=str(uuid.uuid4()),
        username="demo@example.com",
        email="demo@example.com",
        password_hash=pwd_context.hash("demo123"),
        role="client",
        created_at=datetime.utcnow(),
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    print(f"  ✓ Created user: {user.username} (password: demo123)")
    return user


def create_demo_account(db: Session, user: User):
    """Create demo AWS account"""
    print("Creating demo AWS account...")

    # Check if account exists
    existing_account = db.query(Account).filter(Account.user_id == user.id).first()
    if existing_account:
        print("  ✓ Demo account already exists")
        return existing_account

    account = Account(
        id=str(uuid.uuid4()),
        user_id=user.id,
        account_id="123456789012",  # Demo AWS account ID
        account_name="Demo Production Account",
        region="us-east-1",
        status="active",
        connection_method="iam_role",
        role_arn="arn:aws:iam::123456789012:role/DemoRole",
        external_id=str(uuid.uuid4()),
        created_at=datetime.utcnow() - timedelta(days=30),
        updated_at=datetime.utcnow()
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    print(f"  ✓ Created account: {account.account_name} ({account.account_id})")
    return account


def create_demo_instances(db: Session, account: Account):
    """Create realistic EC2 instances"""
    print("Creating demo EC2 instances...")

    # Check if instances exist
    existing = db.query(Instance).filter(Instance.account_id == account.id).count()
    if existing > 0:
        print(f"  ✓ {existing} demo instances already exist")
        return db.query(Instance).filter(Instance.account_id == account.id).all()

    instances_data = [
        # Production instances - well optimized
        {
            "instance_id": "i-prod001",
            "instance_type": "t3.large",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "production", "Name": "web-server-1", "Team": "platform"},
            "cpu_avg": 65.2,
            "memory_avg": 72.1
        },
        {
            "instance_id": "i-prod002",
            "instance_type": "t3.large",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "production", "Name": "web-server-2", "Team": "platform"},
            "cpu_avg": 58.7,
            "memory_avg": 68.3
        },
        {
            "instance_id": "i-prod003",
            "instance_type": "m5.xlarge",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "production", "Name": "api-server-1", "Team": "backend"},
            "cpu_avg": 45.3,
            "memory_avg": 78.9
        },

        # Development instances - opportunities for optimization
        {
            "instance_id": "i-dev001",
            "instance_type": "t3.xlarge",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "development", "Name": "dev-app-1", "Team": "engineering"},
            "cpu_avg": 8.2,  # Very low usage - resize opportunity
            "memory_avg": 12.5
        },
        {
            "instance_id": "i-dev002",
            "instance_type": "t3.large",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "development", "Name": "dev-db-1", "Team": "engineering"},
            "cpu_avg": 15.3,
            "memory_avg": 22.1
        },
        {
            "instance_id": "i-dev003",
            "instance_type": "t3.medium",
            "availability_zone": "us-east-1a",
            "state": "stopped",  # Idle instance
            "lifecycle": "on-demand",
            "tags": {"Environment": "development", "Name": "dev-test-1", "Team": "qa"},
            "cpu_avg": 2.1,
            "memory_avg": 5.3
        },

        # Staging instances - spot opportunity
        {
            "instance_id": "i-staging001",
            "instance_type": "t3.large",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "staging", "Name": "staging-web-1", "Team": "platform"},
            "cpu_avg": 35.2,
            "memory_avg": 42.1
        },
        {
            "instance_id": "i-staging002",
            "instance_type": "t3.medium",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "staging", "Name": "staging-api-1", "Team": "backend"},
            "cpu_avg": 28.7,
            "memory_avg": 38.3
        },

        # ML/Data instances
        {
            "instance_id": "i-ml001",
            "instance_type": "p3.2xlarge",
            "availability_zone": "us-east-1a",
            "state": "stopped",
            "lifecycle": "on-demand",
            "tags": {"Environment": "ml", "Name": "gpu-training-1", "Team": "data-science"},
            "cpu_avg": 0.0,  # Stopped
            "memory_avg": 0.0
        },
        {
            "instance_id": "i-ml002",
            "instance_type": "c5.4xlarge",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "spot",
            "tags": {"Environment": "ml", "Name": "batch-processing-1", "Team": "data-science"},
            "cpu_avg": 82.3,
            "memory_avg": 75.6
        },

        # Database instances
        {
            "instance_id": "i-db001",
            "instance_type": "r5.large",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "production", "Name": "postgres-primary", "Team": "database"},
            "cpu_avg": 42.1,
            "memory_avg": 85.3
        },
        {
            "instance_id": "i-db002",
            "instance_type": "r5.large",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "production", "Name": "postgres-replica", "Team": "database"},
            "cpu_avg": 28.5,
            "memory_avg": 72.1
        },

        # Legacy instances - termination candidates
        {
            "instance_id": "i-legacy001",
            "instance_type": "t2.micro",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "legacy", "Name": "old-app-1", "Team": "platform"},
            "cpu_avg": 1.2,
            "memory_avg": 3.5
        },
        {
            "instance_id": "i-legacy002",
            "instance_type": "t2.small",
            "availability_zone": "us-east-1b",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "legacy", "Name": "old-app-2", "Team": "platform"},
            "cpu_avg": 0.8,
            "memory_avg": 2.1
        },

        # Test instances
        {
            "instance_id": "i-test001",
            "instance_type": "t3.small",
            "availability_zone": "us-east-1a",
            "state": "running",
            "lifecycle": "on-demand",
            "tags": {"Environment": "test", "Name": "integration-test-1", "Team": "qa"},
            "cpu_avg": 12.5,
            "memory_avg": 18.2
        }
    ]

    instances = []
    for data in instances_data:
        instance = Instance(
            id=str(uuid.uuid4()),
            account_id=account.id,
            instance_id=data["instance_id"],
            instance_type=data["instance_type"],
            availability_zone=data["availability_zone"],
            state=data["state"],
            lifecycle=data["lifecycle"],
            instance_metadata={
                "tags": data["tags"],
                "launch_time": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                "cpu_avg": data["cpu_avg"],
                "memory_avg": data["memory_avg"],
                "platform": "Linux/UNIX",
                "architecture": "x86_64"
            },
            created_at=datetime.utcnow() - timedelta(days=30),
            updated_at=datetime.utcnow()
        )
        db.add(instance)
        instances.append(instance)

    db.commit()
    print(f"  ✓ Created {len(instances)} demo instances")
    return instances


def create_cost_data(db: Session, instances: list):
    """Create 30 days of cost optimization data"""
    print("Creating cost optimization data (30 days)...")

    # Check if data exists
    existing = db.query(ExperimentLog).count()
    if existing > 0:
        print(f"  ✓ {existing} experiment logs already exist")
        return

    import random

    # Create daily cost logs for last 30 days
    logs_created = 0
    for instance in instances:
        # Only create cost data for running instances
        if instance.state != "running":
            continue

        # Get pricing based on instance type
        base_prices = {
            "t2.micro": 0.0116,
            "t2.small": 0.023,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "t3.large": 0.0832,
            "t3.xlarge": 0.1664,
            "m5.xlarge": 0.192,
            "c5.4xlarge": 0.68,
            "r5.large": 0.126,
            "p3.2xlarge": 3.06
        }

        old_price = base_prices.get(instance.instance_type, 0.10)

        # Create logs for last 30 days (one per day)
        for days_ago in range(30):
            log_date = datetime.utcnow() - timedelta(days=days_ago)

            # Simulate spot price variations (5-20% cheaper)
            new_price = old_price * random.uniform(0.80, 0.95)
            hourly_savings = old_price - new_price

            # Determine decision based on instance
            metadata = instance.instance_metadata or {}
            tags = metadata.get("tags", {})
            env = tags.get("Environment", "unknown")

            if env in ["development", "staging", "test"]:
                decision = "SWITCH"
                reason = "Cost savings via spot instance for non-production workload"
            elif env == "legacy":
                decision = "TERMINATE"
                reason = "Idle legacy instance with <5% utilization"
            elif hourly_savings > 0.05:
                decision = "SWITCH"
                reason = "Significant cost savings available"
            else:
                decision = "KEEP"
                reason = "Current configuration optimal"

            log = ExperimentLog(
                id=str(uuid.uuid4()),
                instance_id=instance.id,
                execution_time=log_date,
                old_spot_price=round(old_price, 4),
                new_spot_price=round(new_price, 4),
                projected_hourly_savings=round(hourly_savings, 4),
                decision=decision,
                decision_reason=reason,
                experiment_metadata={
                    "instance_type": instance.instance_type,
                    "environment": env,
                    "cpu_utilization": metadata.get("cpu_avg", 0),
                    "memory_utilization": metadata.get("memory_avg", 0)
                },
                created_at=log_date
            )
            db.add(log)
            logs_created += 1

    db.commit()
    print(f"  ✓ Created {logs_created} cost optimization logs")


def main():
    """Main execution"""
    print("=" * 60)
    print("Demo Data Injection Script")
    print("=" * 60)
    print()

    # Get database session
    db = next(get_db_session())

    try:
        # Create demo data
        user = create_demo_user(db)
        account = create_demo_account(db, user)
        instances = create_demo_instances(db, account)
        create_cost_data(db, instances)

        print()
        print("=" * 60)
        print("✅ Demo data injection completed successfully!")
        print("=" * 60)
        print()
        print("Login credentials:")
        print("  Email: demo@example.com")
        print("  Password: demo123")
        print()
        print(f"Account: {account.account_name} ({account.account_id})")
        print(f"Instances: {len(instances)}")
        print(f"Status: {account.status}")
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 1

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    exit(main())
