"""
Migration 016 — WIE v4.6 workload class + spot eligibility fields
==================================================================
Adds three columns to workload_classifications:
  - workload_class:   VARCHAR(20)  "db" | "stateful" | "stateless" | "mixed"
  - spot_eligible:    BOOLEAN      derived: max_spot_replicas > 0
  - total_replicas:   INTEGER      snapshot replica count at classification time

workload_class drives:
  - Distribution Engine execution strategy (SERIAL / BLUE_GREEN / ROLLING)
  - Instance Selection Service capacity_type enforcement
  - UI workload class badges and execution order

spot_eligible replaces the legacy boolean pattern of checking spot_friendly
combined with max_spot_replicas > 0, giving a single unambiguous gate.

total_replicas enables target_builder.build_targets() to validate
min_on_demand_replicas + max_spot_replicas == total_replicas.
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
            print("Adding WIE v4.6 workload class columns...")

            conn.execute(text("""
                ALTER TABLE workload_classifications
                ADD COLUMN IF NOT EXISTS workload_class VARCHAR(20) NOT NULL DEFAULT 'stateless';
            """))
            conn.execute(text("""
                ALTER TABLE workload_classifications
                ADD COLUMN IF NOT EXISTS spot_eligible BOOLEAN NOT NULL DEFAULT false;
            """))
            conn.execute(text("""
                ALTER TABLE workload_classifications
                ADD COLUMN IF NOT EXISTS total_replicas INTEGER NOT NULL DEFAULT 0;
            """))

            # Back-fill spot_eligible from existing max_spot_replicas
            conn.execute(text("""
                UPDATE workload_classifications
                SET spot_eligible = (max_spot_replicas > 0)
                WHERE spot_eligible = false AND max_spot_replicas > 0;
            """))

            # Back-fill workload_class from data_safety + controller_kind
            conn.execute(text("""
                UPDATE workload_classifications
                SET workload_class = 'db'
                WHERE workload_class = 'stateless'
                  AND (
                    data_safety = 'STATEFUL'
                    AND (
                      name ILIKE '%redis%' OR name ILIKE '%postgres%' OR
                      name ILIKE '%mysql%' OR name ILIKE '%mongo%' OR
                      name ILIKE '%elasticsearch%' OR name ILIKE '%kafka%' OR
                      name ILIKE '%zookeeper%' OR name ILIKE '%cassandra%'
                    )
                  );
            """))
            conn.execute(text("""
                UPDATE workload_classifications
                SET workload_class = 'stateful'
                WHERE workload_class = 'stateless'
                  AND controller_kind = 'StatefulSet'
                  AND data_safety = 'STATEFUL';
            """))

            print("Done — workload_class, spot_eligible, total_replicas added.")


def downgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("ALTER TABLE workload_classifications DROP COLUMN IF EXISTS workload_class;"))
            conn.execute(text("ALTER TABLE workload_classifications DROP COLUMN IF EXISTS spot_eligible;"))
            conn.execute(text("ALTER TABLE workload_classifications DROP COLUMN IF EXISTS total_replicas;"))


if __name__ == "__main__":
    upgrade()
