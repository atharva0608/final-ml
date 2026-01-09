
import sys
import os
from sqlalchemy import create_engine, text

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import settings

def update_schema_and_seed():
    print("🔧 Checking database schema...")
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # Check users table for must_reset_password
        try:
            # Try to select the column to see if it exists
            # We use a transaction to avoid breaking the connection state on error in some drivers,
            # though here we catch the exception.
            conn.execute(text("SELECT must_reset_password FROM users LIMIT 1"))
            print("✅ 'must_reset_password' column exists in 'users' table.")
        except Exception:
            print("⚠️ 'must_reset_password' column missing in 'users' table. Adding it...")
            try:
                # Rollback previous failed transaction if any (required for Postgres)
                # But since we're in 'connect()', it might be auto-committing or transaction block.
                # Actually, plain execute might throw.
                # Let's try to proceed. On some DBs, we need to rollback first.
                trans = conn.begin()
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN DEFAULT FALSE NOT NULL"))
                    trans.commit()
                    print("✅ Added 'must_reset_password' column to 'users' table.")
                except Exception as inner_e:
                    trans.rollback()
                    # Try casually without transaction block if automatic
                    try:
                        conn.execute(text("ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN DEFAULT FALSE NOT NULL"))
                        conn.commit()
                        print("✅ Added 'must_reset_password' column to 'users' table (retry).")
                    except:
                        print(f"❌ Failed to add column 'must_reset_password': {inner_e}")
                        
            except Exception as e:
                print(f"❌ Failed to handle schema update for users: {e}")

        # Re-establish connection or ensure clean state for next check?
        # Usually fine to continue if we handled the exception.
        
        # Check organizations table for owner_user_id
        try:
            conn.execute(text("SELECT owner_user_id FROM organizations LIMIT 1"))
            print("✅ 'owner_user_id' column exists in 'organizations' table.")
        except Exception:
            print("⚠️ 'owner_user_id' column missing in 'organizations' table. Adding it...")
            try:
                 # Try adding the column
                # Note: owner_user_id is VARCHAR(36) and nullable
                # We might need to refresh transaction state
                # In SQLAlchemy 1.4/2.0 specifically with Postgres, a failed query invalidates the transaction.
                # It is safer to close and reopen or allow the script to handle it messily. 
                # Ideally we check information_schema instead of 'try-fail'.
                pass
            except:
                pass

    # A better approach: Check information_schema
    print("🔄 Verifying schema via information_schema...")
    with engine.connect() as conn:
        # Check users.must_reset_password
        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='must_reset_password'"))
        if res.rowcount == 0:
             print("➕ Adding 'must_reset_password' to users...")
             conn.execute(text("ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN DEFAULT FALSE"))
             conn.commit()
        
        # Check organizations.owner_user_id
        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='organizations' AND column_name='owner_user_id'"))
        if res.rowcount == 0:
             print("➕ Adding 'owner_user_id' to organizations...")
             conn.execute(text("ALTER TABLE organizations ADD COLUMN owner_user_id VARCHAR(36)"))
             conn.commit()

    print("\n🌱 Running seed data...")
    from scripts.seed_demo_data import seed_demo_data
    seed_demo_data()

if __name__ == "__main__":
    update_schema_and_seed()
