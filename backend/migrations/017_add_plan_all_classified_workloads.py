"""
Migration: Add plan_all_classified_workloads to cluster_optimization_settings
"""
from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")


def upgrade():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    ALTER TABLE cluster_optimization_settings
                    ADD COLUMN IF NOT EXISTS plan_all_classified_workloads BOOLEAN DEFAULT FALSE
                """))
                print("Column 'plan_all_classified_workloads' added to cluster_optimization_settings.")
    except Exception as e:
        print(f"Error adding plan_all_classified_workloads column: {e}")


def downgrade():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    ALTER TABLE cluster_optimization_settings
                    DROP COLUMN IF EXISTS plan_all_classified_workloads
                """))
                print("Column 'plan_all_classified_workloads' removed from cluster_optimization_settings.")
    except Exception as e:
        print(f"Error removing plan_all_classified_workloads column: {e}")


if __name__ == "__main__":
    upgrade()
