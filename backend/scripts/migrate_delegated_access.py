import sys
import os
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import engine
from backend.models.ticket import TicketStatus

def migrate():
    print("Migrating tickets table for Delegated Access...")
    with engine.connect() as conn:
        # 1. Add 'parent_id' column
        try:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN parent_id VARCHAR(36) REFERENCES tickets(id)"))
            print("Added 'parent_id' column.")
        except Exception as e:
            print(f"Skipped 'parent_id' (likely exists): {e}")
            conn.rollback()

        # 2. Add 'activated_at' column
        try:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN activated_at TIMESTAMP"))
            print("Added 'activated_at' column.")
        except Exception as e:
            print(f"Skipped 'activated_at' (likely exists): {e}")
            conn.rollback()

        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
