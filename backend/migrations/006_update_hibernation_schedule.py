
"""
Migration: Update hibernation schedules for multi-cluster support
"""
from sqlalchemy import create_engine, text
import os

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

def upgrade():
    engine = create_engine(DATABASE_URL)
    
    # 1. Create Association Table
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS hibernation_schedule_clusters (
                        schedule_id VARCHAR(36) NOT NULL REFERENCES hibernation_schedules(id) ON DELETE CASCADE,
                        cluster_id VARCHAR(36) NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
                        PRIMARY KEY (schedule_id, cluster_id)
                    )
                """))
                print("Table 'hibernation_schedule_clusters' created.")
    except Exception as e:
        print(f"Error creating association table: {e}")

    # 2. Add new columns to hibernation_schedules
    try:
        with engine.connect() as conn:
            with conn.begin():
                # Add Name
                conn.execute(text("ALTER TABLE hibernation_schedules ADD COLUMN name VARCHAR(100)"))
                print("Column 'name' added.")
                
                # Add Description
                conn.execute(text("ALTER TABLE hibernation_schedules ADD COLUMN description TEXT"))
                print("Column 'description' added.")
                
                # Migrate existing data: Copy cluster_id to association table
                # We do this BEFORE dropping cluster_id
                conn.execute(text("""
                    INSERT INTO hibernation_schedule_clusters (schedule_id, cluster_id)
                    SELECT id, cluster_id FROM hibernation_schedules
                    WHERE cluster_id IS NOT NULL
                    ON CONFLICT DO NOTHING
                """))
                print("Migrated existing cluster_id relationships.")
                
                # Backfill name for existing schedules
                conn.execute(text("UPDATE hibernation_schedules SET name = 'Migrated Schedule' WHERE name IS NULL"))
                conn.execute(text("ALTER TABLE hibernation_schedules ALTER COLUMN name SET NOT NULL"))

                # Drop cluster_id (if it exists)
                # Note: In a strict prod env, we might keep it for a while, but here we clean up
                conn.execute(text("ALTER TABLE hibernation_schedules DROP COLUMN IF EXISTS cluster_id"))
                print("Column 'cluster_id' dropped.")

    except Exception as e:
        print(f"Error updating hibernation_schedules table: {e}")

if __name__ == "__main__":
    upgrade()
