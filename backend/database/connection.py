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

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,  # Max connections in pool
    max_overflow=20,  # Max additional connections
    echo=False,  # Set to True for SQL debugging
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
    - Admin test user (admin/admin)
    - Client test user (ath/ath)
    
    Only runs when ENABLE_TEST_USERS=true environment variable is set.
    """
    # Check if test users should be created
    enable_test_users = os.getenv('ENABLE_TEST_USERS', 'true').lower() == 'true'
    if not enable_test_users:
        print("⚠️  Test user seeding disabled (ENABLE_TEST_USERS != true)")
        return
    
    from .models import User
    from auth.password import get_password_hash
    
    db = SessionLocal()
    try:
        # Check if admin test user exists
        if not db.query(User).filter(User.username == 'admin').first():
            print("🛡️  Seeding Admin (admin)...")
            admin_user = User(
                username='admin',
                email='admin@test.com',
                hashed_password=get_password_hash('admin'),
                role='admin'
            )
            db.add(admin_user)
        
        # Check if client test user exists
        if not db.query(User).filter(User.username == 'ath').first():
            print("👤 Seeding Client (ath)...")
            client_user = User(
                username='ath',
                email='client@test.com',
                hashed_password=get_password_hash('ath'),
                role='client'
            )
            db.add(client_user)
        
        db.commit()
        print("✓ Test users seeded successfully")
    except Exception as e:
        print(f"⚠️  Seeding skipped: {e}")
        db.rollback()
    finally:
        db.close()
