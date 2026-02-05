import sys
import os
sys.path.append('/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.base import Base
from backend.models.user import User
from backend.models.account import Account
from backend.models.cluster import Cluster, ClusterStatus
from backend.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

user_id = "64662c98-491c-4565-8402-11f6a45a5a6f"

try:
    print(f"Checking user {user_id}...")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        print("User not found!")
    else:
        print(f"User found. Org ID: {user.organization_id}")
        
        print("Querying clusters...")
        query = db.query(Cluster).join(Account).filter(
            Account.organization_id == user.organization_id,
            Cluster.status != ClusterStatus.PENDING
        )
        
        print(f"Query SQL: {query}")
        
        clusters = query.all()
        print(f"Found {len(clusters)} clusters.")
        for c in clusters:
            print(f" - {c.name} ({c.status}) Account: {c.account_id}")

        print("Checking raw clusters for account...")
        raw_clusters = db.query(Cluster).all()
        for c in raw_clusters:
            print(f"RAW: {c.name} ({c.status}) Account: {c.account_id}")
            acc = db.query(Account).filter(Account.id == c.account_id).first()
            if acc:
                print(f"  -> Account Org: {acc.organization_id}")
            else:
                print("  -> Account NOT FOUND")

finally:
    db.close()
