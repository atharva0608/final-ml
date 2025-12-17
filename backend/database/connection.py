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
                role='user',  # Use 'user' role for client accounts
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
