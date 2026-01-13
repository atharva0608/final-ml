
"""
Migration: Add status column to users table
"""
from sqlalchemy import create_engine, text
import os

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

def upgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            print("Adding status column to users table...")
            # Check if column exists
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE'"))
                print("Column 'status' added.")
            except Exception as e:
                print(f"Skipping column creation (maybe exists): {e}")

if __name__ == "__main__":
    upgrade()
