from backend.models.base import SessionLocal
from backend.models.user import User
from backend.models.onboarding import OnboardingState

def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"Total Users: {len(users)}")
        for u in users:
            print(f"ID: {u.id} | Email: {u.email} | Role: {u.role} (Type: {type(u.role)})")
    finally:
        db.close()

if __name__ == "__main__":
    list_users()
