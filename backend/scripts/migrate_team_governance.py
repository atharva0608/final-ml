import sys
import os
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

# Add parent directory to path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.models.base import engine

def migrate():
    print("Checking for governance_config column in teams table...")
    with engine.connect() as conn:
        try:
            # Try to select the column to see if it exists
            conn.execute(text("SELECT governance_config FROM teams LIMIT 1"))
            print("Column 'governance_config' already exists.")
        except ProgrammingError:
            print("Column 'governance_config' missing. Adding it...")
            # Rollback the failed transaction from the check
            conn.rollback()
            try:
                # Add the JSON column
                conn.execute(text("ALTER TABLE teams ADD COLUMN governance_config JSONB DEFAULT '{}'"))
                conn.commit()
                print("Successfully added 'governance_config' column.")
            except Exception as e:
                print(f"Failed to add column: {e}")
                conn.rollback()

if __name__ == "__main__":
    migrate()
