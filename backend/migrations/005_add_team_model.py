
"""
Migration: Add teams table and user columns
"""
from sqlalchemy import create_engine, text
import os

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

def upgrade():
    engine = create_engine(DATABASE_URL)
    
    # 1. Create Teams Table
    try:
        with engine.connect() as conn:
            with conn.begin(): # Transaction 1
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS teams (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("Table 'teams' checked/created.")
    except Exception as e:
        print(f"Error creating teams table: {e}")

    # 2. Add columns to users
    
    # full_name
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(100)"))
                print("Column 'full_name' added to users.")
    except Exception as e:
        print(f"Skipping full_name (error or exists): {e}")

    # team_id
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("ALTER TABLE users ADD COLUMN team_id VARCHAR(36) REFERENCES teams(id)"))
                print("Column 'team_id' added to users.")
    except Exception as e:
        print(f"Skipping team_id (error or exists): {e}")

if __name__ == "__main__":
    upgrade()
