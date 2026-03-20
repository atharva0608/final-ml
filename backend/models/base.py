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
# Issue #37: Increase max_overflow to 30 (was 10) to prevent 504s under load.
# pool_recycle=1800 closes idle connections after 30 min to prevent "server closed the connection" errors.
engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")),    # was 10
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),  # recycle connections every 30 min
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


from contextlib import contextmanager

@contextmanager
def get_db_contextmanager():
    """
    Context manager for database sessions in Celery workers and background tasks.
    Usage:
        with get_db_contextmanager() as db:
            db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """
    Create all database tables if they don't exist.
    Uses SQLAlchemy create_all (idempotent — only creates missing tables, never drops existing ones).
    """
    # Import ALL models so they register with Base.metadata before create_all
    from backend.models.organization import Organization
    from backend.models.user import User
    from backend.models.account import Account
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.models.node_template import NodeTemplate, NodeTemplateVersion, ClusterTemplateMapping
    from backend.models.onboarding import OnboardingState
    from backend.models.cluster_policy import ClusterPolicy
    from backend.models.hibernation_schedule import HibernationSchedule
    from backend.models.audit_log import AuditLog
    from backend.models.ml_model import MLModel
    from backend.models.optimization_job import OptimizationJob
    from backend.models.lab_experiment import LabExperiment
    from backend.models.agent_action import AgentAction
    from backend.models.api_key import APIKey
    from backend.models.invitation import OrganizationInvitation
    from backend.models.system_config import SystemConfig
    from backend.models.agent_identity import AgentIdentity
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.termination_event import TerminationEvent
    from backend.models.substitute_state import SubstituteState
    from backend.models.rightsizing_proposal import RightsizingProposal
    from backend.models.approval import Approval
    from backend.models.daily_cluster_stats import DailyClusterStat
    from backend.models.spot_advisor_rates import SpotAdvisorRate
    from backend.models.optimizer_proposal import OptimizerProposal
    from backend.models.substitute_nodes import SubstituteNode
    from backend.models.node_metrics import NodeMetric
    from backend.models.worker_registration import WorkerRegistration
    from backend.models.team import Team
    from backend.models.role import Role
    from backend.models.permission import Permission
    from backend.models.instance_catalog import InstanceCatalog
    from backend.models.billing import DailyCost, CostExplorerSyncStatus
    from backend.models.pricing import SpotPriceHistory, OnDemandPricing, SpotAdvisorData
    from backend.models.platform_settings import PlatformSettings
    from backend.models.tag_policy import TagPolicy
    from backend.models.tag_template import TagTemplate
    from backend.models.tag_automation_rule import TagAutomationRule
    from backend.models.tag_automation_log import TagAutomationLog
    from backend.models.tag_compliance_score import TagComplianceScore
    from backend.models.tag_scoring_config import TagScoringConfig
    from backend.models.cluster_metric import ClusterMetric
    from backend.models.cluster_cooldown import ClusterCooldown
    from backend.models.pool_cooldown import PoolCooldown
    from backend.models.pod_metric import PodMetric
    from backend.models.hygiene_policy import HygienePolicy
    from backend.models.circuit_breaker_state import CircuitBreakerState
    from backend.models.execution_state import ExecutionState
    from backend.models.family_hour_baseline import FamilyHourBaseline
    from backend.models.model_registry import ModelRegistry
    from backend.models.optimizer_state import OptimizerState
    from backend.models.rds_analysis import RDSInstanceAnalysis
    from backend.models.ri_utilization import RIUtilization
    from backend.models.s3_analysis import S3BucketAnalysis
    from backend.models.savings_plan_utilization import SavingsPlanUtilization
    from backend.models.transfer_analysis import DataTransferAnalysis
    from backend.models.chaos_experiment import ChaosExperiment
    try:
        from backend.models.alert_config import AlertConfig
        from backend.models.alert_history import AlertHistory
    except Exception:
        pass
    try:
        from backend.models.authorized_resource import AuthorizedResource
    except Exception:
        pass
    try:
        from backend.models.auto_tag_rule import AutoTagRule
    except Exception:
        pass
    try:
        from backend.models.credential_cache import CredentialCache
    except Exception:
        pass

    # Create all tables (idempotent — only creates tables that don't exist yet)
    Base.metadata.create_all(bind=engine)


def seed_demo_data():
    """
    Create default admin and demo client users if they don't exist.

    SAFETY: Refuses to run in production environments.
    """
    _env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if _env in ("production", "prod"):
        print("⚠️  seed_demo_data() skipped — ENV is production")
        return

    from backend.models.user import User, UserRole, AccessLevel
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
                password_hash=hash_password(os.getenv("SEED_ADMIN_PASSWORD", str(uuid.uuid4()))),
                role=UserRole.SUPER_ADMIN,
                organization_id=admin_org.id,
                # org_role=OrgRole.ORG_ADMIN,
                access_level=AccessLevel.FULL
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Created default admin user: {admin_email} (password from SEED_ADMIN_PASSWORD env var)")
        
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
                password_hash=hash_password(os.getenv("SEED_DEMO_PASSWORD", str(uuid.uuid4()))),
                role=UserRole.CLIENT,
                organization_id=demo_org.id,
                # org_role=OrgRole.ORG_ADMIN,
                access_level=AccessLevel.FULL
            )
            db.add(demo_user)
            db.flush()
            
            # Create Default Account for Demo User
            demo_account = Account(
                aws_account_id="123456789012",
                organization_id=demo_org.id,
                user_id=demo_user.id,
                role_arn="arn:aws:iam::123456789012:role/SpotOptimizerRole",
                status=AccountStatus.ACTIVE
            )
            db.add(demo_account)
            
            db.commit()
            print(f"✅ Created demo client user: {demo_email} (password from SEED_DEMO_PASSWORD env var)")

        # 3. Seed Atharva user (ath@gmail.com / Atharva@123)
        ath_email = "ath@gmail.com"
        ath_user = db.query(User).filter(User.email == ath_email).first()

        if not ath_user:
            # Reuse or create org
            ath_org = db.query(Organization).filter(Organization.slug == "demo-org").first()
            if not ath_org:
                ath_org = Organization(
                    name="Demo Corp",
                    slug="demo-org",
                    status="active"
                )
                db.add(ath_org)
                db.flush()

            ath_user = User(
                email=ath_email,
                password_hash=hash_password("Atharva@123"),
                role=UserRole.SUPER_ADMIN,
                organization_id=ath_org.id,
                access_level=AccessLevel.FULL
            )
            db.add(ath_user)
            db.commit()
            print(f"✅ Created user: {ath_email}")
        else:
            # Ensure password is correct (update if needed)
            from backend.core.crypto import verify_password
            if not verify_password("Atharva@123", ath_user.password_hash):
                ath_user.password_hash = hash_password("Atharva@123")
                db.commit()
                print(f"✅ Updated password for: {ath_email}")

    except Exception as e:
        print(f"⚠️  Failed to seed demo data: {e}")
        db.rollback()
    finally:
        db.close()
