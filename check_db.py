import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from backend.models.base import SessionLocal
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.cluster import Cluster
from backend.models.instance import Instance

db = SessionLocal()
user = db.query(User).filter(User.email == 'ath@gmail.com').first()
if not user:
    print("User not found")
    sys.exit(0)

print(f"User: {user.email}, Org ID: {user.organization_id}")
org = db.query(Organization).filter(Organization.id == user.organization_id).first()
print(f"Org: {org.name}")

# Get clusters for this org
clusters = db.query(Cluster).join(Cluster.account).filter(Cluster.account.has(organization_id=org.id)).all()
print(f"Clusters count: {len(clusters)}")

instances = db.query(Instance).join(Instance.cluster).join(Cluster.account).filter(Cluster.account.has(organization_id=org.id)).all()
print(f"Instances count: {len(instances)}")

