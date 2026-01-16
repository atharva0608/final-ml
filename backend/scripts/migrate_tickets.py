import sys
import os
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import engine, Base
from backend.models.ticket import Ticket
from backend.models.user import User
from backend.models.organization import Organization

def migrate():
    print("Creating 'tickets' table if not exists...")
    try:
        # Create all tables that don't exist
        Base.metadata.create_all(bind=engine)
        print("Successfully created/verified 'tickets' table.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
