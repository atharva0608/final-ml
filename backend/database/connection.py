"""
Database Connection Management

Handles PostgreSQL connection pooling and session management using SQLAlchemy.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Database URL from environment
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/spot_optimizer'
)

# Create engine with production-grade connection pooling
engine = create_engine(
    DATABASE_URL,
    # Connection Health & Pooling
    pool_pre_ping=True,          # CRITICAL: Verify connections before using
    pool_size=10,                # Keep 10 connections open
    max_overflow=20,             # Allow spike to 30 total connections
    pool_timeout=30,             # Wait 30s for available connection
    pool_recycle=1800,           # Refresh connections every 30 mins (prevent stale)
    # Debugging
    echo=False,                  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables

    This should be called on application startup.
    """
    from .models import Base  # Import here to avoid circular imports
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created")


def drop_db():
    """
    Drop all tables (USE WITH CAUTION!)

    Only for development/testing.
    """
    from .models import Base
    Base.metadata.drop_all(bind=engine)
    print("✗ Database tables dropped")

def seed_test_users():
    """
    Seed test users for development and UI testing

    Creates:
    - Admin test user (username: admin, password: admin)
    - Client test user (username: client, password: client)

    Only runs when ENABLE_TEST_USERS=true environment variable is set.
    """
    # Check if test users should be created
    enable_test_users = os.getenv('ENABLE_TEST_USERS', 'true').lower() == 'true'
    if not enable_test_users:
        print("⚠️  Test user seeding disabled (ENABLE_TEST_USERS != true)")
        return

    from .models import User
    from auth.password import hash_password

    db = SessionLocal()
    try:
        # Check if admin test user exists
        if not db.query(User).filter(User.username == 'admin').first():
            print("🛡️  Seeding Admin (username: admin, password: admin)...")
            admin_user = User(
                username='admin',
                email='admin@test.com',
                hashed_password=hash_password('admin'),
                role='admin',
                full_name='System Administrator',
                is_active=True
            )
            db.add(admin_user)
        else:
            print("✓ Admin user already exists")

        # Check if client test user exists
        if not db.query(User).filter(User.username == 'client').first():
            print("👤 Seeding Client (username: client, password: client)...")
            client_user = User(
                username='client',
                email='client@test.com',
                hashed_password=hash_password('client'),
                role='client',  # Lowercase 'client' role for client dashboard access
                full_name='Test Client User',
                is_active=True
            )
            db.add(client_user)
        else:
            print("✓ Client user already exists")

        db.commit()
        print("✓ Test users seeded successfully")
    except Exception as e:
        print(f"⚠️  Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()


def seed_demo_data():
    """
    Seed demo data for one client account with AWS instances and cost data

    Creates:
    - Demo client user (username: democlient, password: demo123)
    - One AWS account (account_id: 123456789012)
    - 15 EC2 instances with varied configurations
    - 30 days of cost optimization experiment logs

    Only runs when ENABLE_DEMO_DATA=true environment variable is set.
    This provides realistic data for UI testing and demonstrations.
    """
    # Check if demo data should be created
    enable_demo_data = os.getenv('ENABLE_DEMO_DATA', 'false').lower() == 'true'
    if not enable_demo_data:
        print("⚠️  Demo data seeding disabled (ENABLE_DEMO_DATA != true)")
        return

    from .models import User, Account, Instance, ExperimentLog
    from auth.password import hash_password
    from datetime import datetime, timedelta
    import random

    db = SessionLocal()
    try:
        print("📊 Starting demo data seeding...")

        # 1. Create demo client user
        demo_user = db.query(User).filter(User.username == 'democlient').first()
        if not demo_user:
            print("👤 Creating demo client user (username: democlient, password: demo123)...")
            demo_user = User(
                username='democlient',
                email='democlient@example.com',
                hashed_password=hash_password('demo123'),
                role='client',
                full_name='Demo Client User',
                is_active=True
            )
            db.add(demo_user)
            db.flush()  # Get the user ID
        else:
            print("✓ Demo client user already exists")

        # 2. Create demo AWS account
        demo_account = db.query(Account).filter(Account.account_id == '123456789012').first()
        if not demo_account:
            print("☁️  Creating demo AWS account (123456789012)...")
            demo_account = Account(
                user_id=demo_user.id,
                account_id='123456789012',
                account_name='Demo AWS Production',
                environment_type='PROD',
                connection_method='iam_role',
                role_arn='arn:aws:iam::123456789012:role/SpotOptimizerRole',
                external_id='demo-external-id-12345',
                region='us-east-1',
                status='active',
                is_active=True,
                account_metadata={
                    'total_instances': 15,
                    'monthly_cost': 7143.71,
                    'optimization_enabled': True
                }
            )
            db.add(demo_account)
            db.flush()  # Get the account ID
        else:
            print("✓ Demo AWS account already exists")

        # 3. Create 15 demo EC2 instances
        existing_instances = db.query(Instance).filter(Instance.account_id == demo_account.id).count()
        if existing_instances == 0:
            print("🖥️  Creating 15 demo EC2 instances...")

            instance_configs = [
                # Production workloads
                {'type': 't3.medium', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 't3.large', 'az': 'us-east-1b', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 't3.xlarge', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'c5.large', 'az': 'us-east-1c', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'c5.xlarge', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                # Memory-optimized workloads
                {'type': 'r5.large', 'az': 'us-east-1b', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'r5.xlarge', 'az': 'us-east-1c', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'r5.2xlarge', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                # Compute-optimized
                {'type': 'c5.2xlarge', 'az': 'us-east-1b', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'c5.4xlarge', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                # Lab instances
                {'type': 't3.small', 'az': 'us-east-1c', 'mode': 'LINEAR', 'orchestrator': 'STANDALONE'},
                {'type': 't3.medium', 'az': 'us-east-1a', 'mode': 'LINEAR', 'orchestrator': 'STANDALONE'},
                # GPU workloads
                {'type': 'g4dn.xlarge', 'az': 'us-east-1b', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                {'type': 'g4dn.2xlarge', 'az': 'us-east-1a', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
                # General purpose
                {'type': 'm5.large', 'az': 'us-east-1c', 'mode': 'CLUSTER', 'orchestrator': 'KUBERNETES'},
            ]

            instances = []
            for idx, config in enumerate(instance_configs, start=1):
                instance = Instance(
                    account_id=demo_account.id,
                    instance_id=f'i-{idx:08d}demo{random.randint(1000, 9999)}',
                    instance_type=config['type'],
                    availability_zone=config['az'],
                    pipeline_mode=config['mode'],
                    orchestrator_type=config['orchestrator'],
                    is_shadow_mode=False,
                    auth_status='AUTHORIZED',
                    is_active=True,
                    cluster_membership={
                        'cluster_name': 'demo-eks-cluster' if config['orchestrator'] == 'KUBERNETES' else None,
                        'node_group': 'workers',
                        'role': 'worker'
                    } if config['orchestrator'] == 'KUBERNETES' else None,
                    instance_metadata={
                        'demo': True,
                        'created_for': 'ui_testing',
                        'cost_per_hour': round(random.uniform(0.05, 2.5), 4)
                    }
                )
                db.add(instance)
                instances.append(instance)

            db.flush()  # Get instance IDs
            print(f"✓ Created {len(instances)} demo instances")

            # 4. Create 30 days of experiment logs (cost optimization data)
            print("📈 Creating 30 days of experiment logs...")

            log_count = 0
            base_date = datetime.utcnow() - timedelta(days=30)

            for instance in instances[:10]:  # Only create logs for first 10 instances to keep it realistic
                # Create 3-5 logs per day for each instance
                for day in range(30):
                    logs_per_day = random.randint(3, 5)
                    for log_idx in range(logs_per_day):
                        timestamp = base_date + timedelta(
                            days=day,
                            hours=random.randint(0, 23),
                            minutes=random.randint(0, 59)
                        )

                        # Randomly decide if switch was made
                        made_switch = random.random() < 0.3  # 30% of evaluations result in switch

                        if made_switch:
                            old_price = round(random.uniform(0.05, 0.50), 4)
                            new_price = round(old_price * random.uniform(0.60, 0.85), 4)  # 15-40% savings

                            log = ExperimentLog(
                                instance_id=instance.id,
                                pipeline_mode=instance.pipeline_mode,
                                is_shadow_run=False,
                                prediction_score=round(random.uniform(0.70, 0.95), 4),
                                decision='SWITCH',
                                decision_reason='Cost optimization opportunity detected',
                                execution_time=timestamp,
                                execution_duration_ms=random.randint(50, 300),
                                candidates_evaluated=random.randint(5, 20),
                                selected_instance_type=instance.instance_type,
                                selected_availability_zone=instance.availability_zone,
                                old_spot_price=old_price,
                                new_spot_price=new_price,
                                projected_hourly_savings=round(old_price - new_price, 4),
                                features_used={
                                    'spot_price': new_price,
                                    'cpu_utilization': round(random.uniform(0.4, 0.9), 2),
                                    'memory_utilization': round(random.uniform(0.5, 0.85), 2),
                                    'interruption_rate': round(random.uniform(0.01, 0.15), 3)
                                }
                            )
                        else:
                            # HOLD decision
                            log = ExperimentLog(
                                instance_id=instance.id,
                                pipeline_mode=instance.pipeline_mode,
                                is_shadow_run=False,
                                prediction_score=round(random.uniform(0.30, 0.65), 4),
                                decision='HOLD',
                                decision_reason='Current configuration is optimal',
                                execution_time=timestamp,
                                execution_duration_ms=random.randint(30, 150),
                                candidates_evaluated=random.randint(3, 10),
                                features_used={
                                    'spot_price': round(random.uniform(0.05, 0.50), 4),
                                    'cpu_utilization': round(random.uniform(0.4, 0.9), 2),
                                    'memory_utilization': round(random.uniform(0.5, 0.85), 2)
                                }
                            )

                        db.add(log)
                        log_count += 1

            print(f"✓ Created {log_count} experiment logs")

        else:
            print(f"✓ Demo instances already exist ({existing_instances} instances)")

        db.commit()
        print("✅ Demo data seeding completed successfully!")
        print(f"   - User: democlient / demo123")
        print(f"   - AWS Account: 123456789012 (Demo AWS Production)")
        print(f"   - Region: us-east-1")
        print(f"   - Status: active")

    except Exception as e:
        print(f"❌ Demo data seeding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
