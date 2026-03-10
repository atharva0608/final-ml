import sys
import os
import logging
from datetime import datetime

# Enable sqlalchemy logging to see the exact SQL queries
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

sys.path.insert(0, os.path.abspath('.'))
from backend.models.base import SessionLocal
from backend.models.cluster import Cluster, ClusterStatus

db = SessionLocal()
cluster = db.query(Cluster).filter(Cluster.id == 'ce8f944c-5aa0-4e5d-b0f7-f4e29dd73a9d').first()
if not cluster:
    print("Cluster not found")
    sys.exit()

print(f"Before: status={cluster.status}, agent={cluster.agent_installed}, hb={cluster.last_heartbeat}")

cluster.last_heartbeat = datetime.utcnow()
cluster.status = ClusterStatus.ACTIVE
cluster.agent_installed = "Y"

print(f"Modified: status={cluster.status}, agent={cluster.agent_installed}, hb={cluster.last_heartbeat}")

db.commit()

cluster_after = db.query(Cluster).filter(Cluster.id == 'ce8f944c-5aa0-4e5d-b0f7-f4e29dd73a9d').first()
print(f"After DB commit: status={cluster_after.status}, agent={cluster_after.agent_installed}")
