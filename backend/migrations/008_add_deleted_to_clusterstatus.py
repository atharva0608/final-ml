"""
Migration: Add DELETED value to clusterstatus enum

This is idempotent — uses IF NOT EXISTS so it can safely be re-run.
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
                    ALTER TYPE clusterstatus ADD VALUE IF NOT EXISTS 'DELETED'
                """))
                print("Added 'DELETED' to clusterstatus enum (or already present).")
    except Exception as e:
        print(f"Error adding DELETED to clusterstatus enum: {e}")


def downgrade():
    # PostgreSQL does not support removing values from enums.
    # To reverse, you'd need to recreate the enum type entirely.
    print("Downgrade not supported — cannot remove enum values in PostgreSQL.")


if __name__ == "__main__":
    upgrade()
