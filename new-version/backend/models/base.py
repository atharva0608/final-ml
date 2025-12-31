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
