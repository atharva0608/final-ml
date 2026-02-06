
import sys
import os
from datetime import datetime
from getpass import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import SessionLocal
from backend.models.system_config import SystemConfig

def setup_platform_creds():
    print("🔐 Spot Optimizer - Platform Credential Setup")
    print("--------------------------------------------")
    print("This script securely stores your AWS Platform Credentials in the database.")
    print("These credentials are used by the Discovery Worker to assume roles in linked accounts.")
    
    access_key = input("Enter AWS Access Key ID: ").strip()
    if not access_key:
        print("Error: Access Key cannot be empty")
        return
        
    secret_key = getpass("Enter AWS Secret Access Key: ").strip()
    if not secret_key:
        print("Error: Secret Key cannot be empty")
        return
        
    region = input("Enter AWS Region [us-east-1]: ").strip() or "us-east-1"
    
    db = SessionLocal()
    try:
        # Update or Create Config Entries
        configs = {
            "PLATFORM_AWS_ACCESS_KEY": access_key,
            "PLATFORM_AWS_SECRET": secret_key,
            "PLATFORM_AWS_REGION": region
        }
        
        for key, value in configs.items():
            config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if config:
                config.value = value
                config.updated_at = datetime.utcnow()
                print(f"Updated {key}")
            else:
                config = SystemConfig(
                    key=key,
                    value=value,
                    description=f"Platform AWS Credential ({key})",
                    is_encrypted=True if "SECRET" in key else False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(config)
                print(f"Created {key}")
        
        db.commit()
        print("\n✅ Successfully stored Platform Credentials in database!")
        print("Please restart the backend/worker services to apply changes.")
        
    except Exception as e:
        print(f"\n❌ Error saving credentials: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_platform_creds()
