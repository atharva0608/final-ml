import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.models.base import SessionLocal
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.team import Team
from datetime import datetime

db = SessionLocal()
try:
    demo = db.query(User).filter(User.email=="demo@spotoptimizer.com").first()
    if not demo:
        print("Demo user missing")
        sys.exit(1)
        
    org = db.query(Organization).first()
    if not org:
        org = Organization(id=str(uuid.uuid4()), name="Demo Org", stripe_customer_id="cus_demo", subscription_status="active", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(org)
    
    demo.organization_id = org.id

    team = db.query(Team).filter(Team.name=="cloud").first()
    if not team:
        team = Team(id=str(uuid.uuid4()), organization_id=org.id, name="cloud", description="Cloud team", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(team)
    
    demo.team_id = team.id
    db.commit()
    print("Org and team created successfully!")
except Exception as e:
    print(f"Error: {e}")
    db.rollback()
finally:
    db.close()
