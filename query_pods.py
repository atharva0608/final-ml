import sys
sys.path.insert(0, '/Users/atharvapudale/Desktop/backend-ecc/Atharva Repo/github/final-ml')
from backend.db.session import SessionLocal
from backend.models.pod_metric import PodMetric
from sqlalchemy import func
from datetime import datetime, timedelta

db = SessionLocal()
cluster_id = "d2fce9ce-405d-4e26-bf9c-9c203d1fbb3f"
now = datetime.utcnow()

pods = db.query(PodMetric.pod_name, PodMetric.phase, PodMetric.timestamp).filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.pod_name.like("%spot-orchestrator%")
).order_by(PodMetric.pod_name, PodMetric.timestamp.desc()).all()

# manual distinct
seen = set()
for p in pods:
    if p.pod_name not in seen:
        age_minutes = (now - p.timestamp).total_seconds() / 60.0
        print(f"Pod: {p.pod_name}, Phase: {p.phase}, Age: {age_minutes:.1f}m, Timestamp: {p.timestamp}")
        seen.add(p.pod_name)
