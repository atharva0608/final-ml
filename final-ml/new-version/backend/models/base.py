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
    from backend.models.user import User
    from backend.models.account import Account
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.models.node_template import NodeTemplate
    from backend.models.cluster_policy import ClusterPolicy
    from backend.models.hibernation_schedule import HibernationSchedule
    from backend.models.audit_log import AuditLog
    from backend.models.ml_model import MLModel
    from backend.models.optimization_job import OptimizationJob
    from backend.models.lab_experiment import LabExperiment
    from backend.models.agent_action import AgentAction
    from backend.models.api_key import APIKey

    # Create all tables
    Base.metadata.create_all(bind=engine)


def seed_default_admin():
    """
    Create default admin user if no users exist
    """
    from backend.models.user import User
    from backend.core.crypto import hash_password

    db = SessionLocal()
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        if user_count == 0:
            # Create default admin user
            admin_user = User(
                email="admin@spotoptimizer.com",
                password_hash=hash_password("admin123"),
                role="SUPER_ADMIN"
            )
            db.add(admin_user)
            db.commit()
            print("✅ Created default admin user: admin@spotoptimizer.com / admin123")
    except Exception as e:
        print(f"⚠️  Failed to create default admin user: {e}")
        db.rollback()
    finally:
        db.close()
