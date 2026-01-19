import sys
import os
import uuid
from sqlalchemy import text

# Add parent directory to path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.models.base import SessionLocal, engine
from backend.models.organization import Organization

def migrate_organizations():
    db = SessionLocal()
    try:
        print("Checking for external_id column in organizations table...")
        
        # Check if column exists
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='organizations' AND column_name='external_id'"))
        if not result.fetchone():
            print("Adding external_id column...")
            db.execute(text("ALTER TABLE organizations ADD COLUMN external_id VARCHAR(36)"))
            db.execute(text("CREATE UNIQUE INDEX ix_organizations_external_id ON organizations (external_id)"))
            db.commit()
            print("Column added.")
        else:
            print("Column already exists.")
            
        # Backfill existing organizations
        print("Backfilling existing organizations...")
        orgs = db.query(Organization).filter(Organization.external_id == None).all()
        
        count = 0
        for org in orgs:
            org.external_id = str(uuid.uuid4())
            count += 1
            
        if count > 0:
            db.commit()
            print(f"Backfilled {count} organizations with new external_ids.")
        else:
            print("All organizations already have external_ids.")
            
        print("Migration complete!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_organizations()
