"""
Migration script to add 'preferences' JSON column to users table.

Run with: docker exec spot-optimizer-backend python backend/scripts/migrate_user_preferences.py
"""

import sys
sys.path.insert(0, '/app')

from backend.models.base import engine
from sqlalchemy import text

def migrate():
    """Add preferences column to users table"""
    
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'preferences'
        """))
        
        if result.fetchone():
            print("Column 'preferences' already exists. Skipping.")
            return
        
        # Add the column
        conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN preferences JSON DEFAULT NULL
        """))
        conn.commit()
        
        print("Successfully added 'preferences' column to users table.")

if __name__ == "__main__":
    migrate()
