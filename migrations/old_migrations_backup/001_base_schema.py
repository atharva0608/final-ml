"""
Base schema migration - Consolidated from all previous migrations

This single migration contains the complete database schema, dumped from
the live database after all 42 individual migrations were applied.

Uses a separate AUTOCOMMIT connection to execute each statement independently
so that pg_dump boilerplate failures don't cascade.

Revision ID: 001
Revises: None
Create Date: 2026-03-07

"""
from alembic import op
from sqlalchemy import create_engine, text
import os

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def _split_sql(sql_content):
    """Split pg_dump SQL into individual executable statements."""
    statements = []
    current = []
    in_dollar_quote = False

    for line in sql_content.split('\n'):
        stripped = line.strip()

        # Skip empty lines and pure comments
        if not stripped or stripped.startswith('--'):
            continue

        # Track dollar quoting (used in CREATE FUNCTION, etc.)
        dollar_count = line.count('$$')
        if dollar_count % 2 == 1:
            in_dollar_quote = not in_dollar_quote

        current.append(line)

        # Statement ends at semicolon (but not inside dollar quotes)
        if stripped.endswith(';') and not in_dollar_quote:
            stmt = '\n'.join(current).strip().rstrip(';').strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = '\n'.join(current).strip().rstrip(';').strip()
        if stmt:
            statements.append(stmt)

    return statements


def upgrade() -> None:
    schema_path = os.path.join(os.path.dirname(__file__), 'base_schema.sql')
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    statements = _split_sql(schema_sql)

    # Create a separate engine with AUTOCOMMIT to bypass Alembic's transaction
    # Use DATABASE_URL from env because str(engine.url) masks the password
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        bind = op.get_bind()
        db_url = bind.engine.url.render_as_string(hide_password=False)
    engine = create_engine(db_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                err = str(e).lower()
                if 'already exists' in err or 'duplicate' in err:
                    pass
                else:
                    print(f"  SKIP: {str(e)[:150]}")

        # Initialize TimescaleDB hypertables post-schema creation
        try:
            print("Configuring TimescaleDB Hypertables...")
            
            # TimescaleDB will recreate these properly. We MUST drop them if pg_dump left them behind
            # otherwise create_hypertable will crash with 'trigger "ts_insert_blocker" already exists'
            conn.execute(text("DROP TRIGGER IF EXISTS ts_insert_blocker ON pod_metrics;"))
            conn.execute(text("DROP TRIGGER IF EXISTS ts_insert_blocker ON node_metrics;"))
            conn.execute(text("DROP TRIGGER IF EXISTS ts_insert_blocker ON cluster_metrics;"))

            conn.execute(text("SELECT create_hypertable('pod_metrics', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"))
            conn.execute(text("SELECT create_hypertable('node_metrics', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"))
            conn.execute(text("SELECT create_hypertable('cluster_metrics', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"))
        except Exception as e:
            print(f"  FAILED to initialize hypertables: {str(e)[:150]}")

    engine.dispose()


def downgrade() -> None:
    op.execute("DROP SCHEMA public CASCADE")
    op.execute("CREATE SCHEMA public")
