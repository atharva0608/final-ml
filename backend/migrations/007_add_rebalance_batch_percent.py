"""
Migration: Add rebalance_batch_percent to cluster_optimization_settings
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
                    ADD COLUMN IF NOT EXISTS rebalance_batch_percent INTEGER DEFAULT NULL
                """))
                print("Column 'rebalance_batch_percent' added to cluster_optimization_settings.")
    except Exception as e:
        print(f"Error adding rebalance_batch_percent column: {e}")


def downgrade():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    ALTER TABLE cluster_optimization_settings
                    DROP COLUMN IF EXISTS rebalance_batch_percent
                """))
                print("Column 'rebalance_batch_percent' removed from cluster_optimization_settings.")
    except Exception as e:
        print(f"Error removing rebalance_batch_percent column: {e}")


if __name__ == "__main__":
    upgrade()
