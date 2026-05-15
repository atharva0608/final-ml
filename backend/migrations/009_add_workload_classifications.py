"""
Migration: Create workload_classifications table (WIE v4.3)
===========================================================
Creates the table for storing workload classification records.
Write-suppression is handled in the engine — migration creates
all columns and indexes required by the engine.
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
            print("Creating workload_classifications table...")

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workload_classifications (
                    id                  VARCHAR(36)     PRIMARY KEY,
                    cluster_id          VARCHAR(36)     NOT NULL
                        REFERENCES clusters(id) ON DELETE CASCADE,
                    workload_id         VARCHAR(512)    NOT NULL,
                    namespace           VARCHAR(253)    NOT NULL,
                    name                VARCHAR(253)    NOT NULL,
                    controller_kind     VARCHAR(50)     NOT NULL,

                    role                VARCHAR(20)     NOT NULL,
                    criticality_score   INTEGER         NOT NULL,
                    tier                VARCHAR(20)     NOT NULL,
                    spot_score          INTEGER         NOT NULL,
                    spot_friendly       BOOLEAN         NOT NULL,
                    confidence_score    INTEGER         NOT NULL,
                    confidence_state    VARCHAR(20)     NOT NULL,
                    data_safety         VARCHAR(20)     NOT NULL,

                    signals_fired       JSONB           NOT NULL DEFAULT '[]',
                    override_active     BOOLEAN         NOT NULL DEFAULT FALSE,
                    override_reason     VARCHAR(512),
                    input_hash          VARCHAR(100)    NOT NULL DEFAULT '',
                    schema_version      VARCHAR(10)     NOT NULL DEFAULT '4.3',

                    classified_at       TIMESTAMP       NOT NULL DEFAULT NOW(),
                    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
                    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
                )
            """))
            print("Table created.")

            # Unique constraint: one record per workload per cluster
            conn.execute(text("""
                DO $$ BEGIN
                    ALTER TABLE workload_classifications
                        ADD CONSTRAINT uq_workload_classification_cluster_workload
                            UNIQUE (cluster_id, workload_id);
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
            """))

            # Indexes
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_wc_cluster_tier
                    ON workload_classifications (cluster_id, tier)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_wc_cluster_confidence
                    ON workload_classifications (cluster_id, confidence_state)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_wc_cluster_spot
                    ON workload_classifications (cluster_id, spot_friendly, confidence_state)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_wc_workload_id
                    ON workload_classifications (workload_id)
            """))

            print("Indexes created.")
            print("Migration complete: workload_classifications ready.")


def downgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            print("Dropping workload_classifications table...")
            conn.execute(text("DROP TABLE IF EXISTS workload_classifications CASCADE"))
            print("Table dropped.")


if __name__ == "__main__":
    upgrade()
