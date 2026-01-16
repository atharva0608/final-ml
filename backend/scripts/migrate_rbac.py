import sys
import os
import logging
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.config import get_settings
from backend.models.base import Base
# Import models to ensure they are registered with Base.metadata
from backend.models.permission import Permission
from backend.models.role import Role, role_permissions
from backend.models.user import User, user_permissions
from backend.models.organization import Organization

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_rbac():
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        logger.info("Starting RBAC Migration...")
        
        # 1. Drop existing tables (Order matters due to FKs)
        logger.info("Dropping tables...")
        # role_permissions depends on roles and permissions
        # user_permissions depends on users and permissions
        # roles depend on nothing (except org)
        # permissions depend on nothing
        
        # We need to drop association tables first
        role_permissions.drop(engine, checkfirst=True)
        user_permissions.drop(engine, checkfirst=True)
        
        # Now drop permissions (Role table doesn't need to be dropped ideally, 
        # but if we change Role model we might need to. Permission model DEFINITELY changed.)
        Permission.__table__.drop(engine, checkfirst=True)
        
        logger.info("Tables dropped successfully.")
        
        # 2. Recreate tables
        logger.info("Recreating tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Tables recreated successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # Print full stack trace
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    migrate_rbac()
