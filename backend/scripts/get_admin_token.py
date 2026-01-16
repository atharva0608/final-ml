import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.crypto import create_access_token
from backend.models.base import SessionLocal
from backend.models.user import User
# Fix relationships
from backend.models.organization import Organization
from backend.models.onboarding import OnboardingState
from backend.models.role import Role

def get_token():
    db = SessionLocal()
    try:
        # Find an ORG_ADMIN
        user = db.query(User).filter(User.role == 'ORG_ADMIN').first()
        if not user:
            # Fallback to any user
            user = db.query(User).first()
        
        if not user:
            print("No users found")
            return

        token = create_access_token({"sub": str(user.id)})
        print(token)
    finally:
        db.close()

if __name__ == "__main__":
    get_token()
