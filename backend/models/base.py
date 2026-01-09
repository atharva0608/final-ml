"""
Base model and database session configuration
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime
import uuid

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    echo=os.getenv("DB_ECHO", "False").lower() == "true",
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def generate_uuid():
    """Generate UUID for primary keys"""
    return str(uuid.uuid4())


def get_db():
    """
    Dependency for FastAPI routes to get database session
    Usage:
        @app.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Create all database tables if they don't exist
    This is called on application startup
    """
    # Import all models to ensure they're registered with Base
    from backend.models.organization import Organization
    from backend.models.user import User
    from backend.models.account import Account
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.models.node_template import NodeTemplate
    from backend.models.onboarding import OnboardingState
    from backend.models.cluster_policy import ClusterPolicy
    from backend.models.hibernation_schedule import HibernationSchedule
    from backend.models.audit_log import AuditLog
    from backend.models.ml_model import MLModel
    from backend.models.optimization_job import OptimizationJob
    from backend.models.lab_experiment import LabExperiment
    from backend.models.agent_action import AgentAction
    from backend.models.agent_action import AgentAction
    from backend.models.api_key import APIKey
    from backend.models.invitation import OrganizationInvitation

    # Create all tables
    Base.metadata.create_all(bind=engine)


def seed_demo_data():
    """
    Create default admin and demo client users if they don't exist
    """
    from backend.models.user import User, UserRole, OrgRole, AccessLevel
    from backend.models.organization import Organization
    from backend.models.account import Account, AccountStatus
    from backend.core.crypto import hash_password

    db = SessionLocal()
    try:
        # 1. Seed Admin
        admin_email = "admin@spotoptimizer.com"
        admin_user = db.query(User).filter(User.email == admin_email).first()
        
        if not admin_user:
            # Check/Create Admin Org
            admin_org = db.query(Organization).filter(Organization.slug == "admin-org").first()
            if not admin_org:
                admin_org = Organization(
                    name="Admin Organization",
                    slug="admin-org",
                    status="active"
                )
                db.add(admin_org)
                db.flush()
            
            # Create Admin User
            admin_user = User(
                email=admin_email,
                password_hash=hash_password("admin123"),
                role=UserRole.SUPER_ADMIN,
                organization_id=admin_org.id,
                org_role=OrgRole.ORG_ADMIN,
                access_level=AccessLevel.FULL
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Created default admin user: {admin_email} / admin123")
        
        # 2. Seed Demo Client
        demo_email = "demo@spotoptimizer.com"
        demo_user = db.query(User).filter(User.email == demo_email).first()
        
        if not demo_user:
            # Check/Create Demo Org
            demo_org = db.query(Organization).filter(Organization.slug == "demo-org").first()
            if not demo_org:
                demo_org = Organization(
                    name="Demo Corp",
                    slug="demo-org",
                    status="active"
                )
                db.add(demo_org)
                db.flush()
            
            # Create Demo User
            demo_user = User(
                email=demo_email,
                password_hash=hash_password("demo1234"),
                role=UserRole.CLIENT,
                organization_id=demo_org.id,
                org_role=OrgRole.ORG_ADMIN,
                access_level=AccessLevel.FULL
            )
            db.add(demo_user)
            db.flush()
            
            # Create Default Account for Demo User
            demo_account = Account(
                aws_account_id="123456789012",
                organization_id=demo_org.id,
                role_arn="arn:aws:iam::123456789012:role/SpotOptimizerRole",
                status=AccountStatus.ACTIVE
            )
            db.add(demo_account)
            
            db.commit()
            print(f"✅ Created demo client user: {demo_email} / demo1234")

    except Exception as e:
        print(f"⚠️  Failed to seed demo data: {e}")
        db.rollback()
    finally:
        db.close()
