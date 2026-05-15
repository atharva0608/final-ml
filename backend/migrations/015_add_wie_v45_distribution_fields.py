"""
Migration 015 — WIE v4.5 spot distribution constraint fields
=============================================================
Adds two Integer columns to workload_classifications:
  - min_on_demand_replicas: minimum OD replicas required for safe operation
  - max_spot_replicas:      maximum spot replicas allowed

Both default to 0 for existing rows (conservative — callers treat 0 as
"no distribution computed yet" and fall back to spot_friendly boolean).

After the next WIE slow-loop cycle these will be populated from
compute_spot_distribution() for all active workloads.
"""
from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/spot_optimizer",
)


def upgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            print("Adding WIE v4.5 spot distribution columns...")

            conn.execute(text("""
                ALTER TABLE workload_classifications
                ADD COLUMN IF NOT EXISTS min_on_demand_replicas INTEGER NOT NULL DEFAULT 0;
            """))
            conn.execute(text("""
                ALTER TABLE workload_classifications
                ADD COLUMN IF NOT EXISTS max_spot_replicas INTEGER NOT NULL DEFAULT 0;
            """))

            print("Done — min_on_demand_replicas and max_spot_replicas added.")


def downgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("ALTER TABLE workload_classifications DROP COLUMN IF EXISTS min_on_demand_replicas;"))
            conn.execute(text("ALTER TABLE workload_classifications DROP COLUMN IF EXISTS max_spot_replicas;"))


if __name__ == "__main__":
    upgrade()
