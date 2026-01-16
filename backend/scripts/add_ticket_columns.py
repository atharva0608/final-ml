import os
import sys
import sqlalchemy
from sqlalchemy import create_engine, text

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.core.config import settings

def migrate():
    print(f"Connecting to database: {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        print("Checking for missing columns in 'tickets' table...")
        
        # Check parent_id
        try:
            conn.execute(text("SELECT parent_id FROM tickets LIMIT 1"))
            print(" - 'parent_id' column exists.")
        except sqlalchemy.exc.ProgrammingError:
            print(" - 'parent_id' column MISSING. Adding it...")
            conn.execute(text("ROLLBACK")) # Clear error state
            conn.execute(text("ALTER TABLE tickets ADD COLUMN parent_id VARCHAR(36)"))
            conn.execute(text("CREATE INDEX ix_tickets_parent_id ON tickets (parent_id)"))
            conn.execute(text("ALTER TABLE tickets ADD CONSTRAINT fk_tickets_parent_id FOREIGN KEY (parent_id) REFERENCES tickets(id)"))
            print("   -> Added 'parent_id'.")

        # Check activated_at
        try:
            conn.execute(text("SELECT activated_at FROM tickets LIMIT 1"))
            print(" - 'activated_at' column exists.")
        except sqlalchemy.exc.ProgrammingError:
            print(" - 'activated_at' column MISSING. Adding it...")
            conn.execute(text("ROLLBACK"))
            conn.execute(text("ALTER TABLE tickets ADD COLUMN activated_at TIMESTAMP WITHOUT TIME ZONE"))
            print("   -> Added 'activated_at'.")

        
        # Check if PENDING_CONSENT enum value exists (Postgres ENUMs are static)
        # It's harder to check ENUM content via pure SQL safely without knowing specific type name if auto-generated.
        # But usually in dev we can just alter type or letting SQLAlchemy handle it if we used Alembic.
        # Here we manually try to alter type to add value.
        try:
            conn.execute(text("ALTER TYPE ticketstatus ADD VALUE 'PENDING_CONSENT'"))
            print(" - Added 'PENDING_CONSENT' to TicketStatus enum.")
        except sqlalchemy.exc.ProgrammingError as e:
            conn.execute(text("ROLLBACK"))
            print(" - 'PENDING_CONSENT' likely already in enum or error:", e)

        print("\nMigration completed.")
        conn.commit()

if __name__ == "__main__":
    migrate()
