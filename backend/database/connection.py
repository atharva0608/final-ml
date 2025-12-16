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
