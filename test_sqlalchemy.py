import sys
import os
sys.path.insert(0, '/Users/atharvapudale/Desktop/backend-ecc/Atharva Repo/github/final-ml')

from backend.db.database import SessionLocal
from backend.models.node_metadata import NodeMetadata
from backend.models.pod_metric import PodMetric
from sqlalchemy import func
from datetime import datetime, timedelta

db = SessionLocal()
cluster_id = 'd2fce9ce-405d-4e26-bf9c-9c203d1fbb3f'
_pod_cutoff = datetime.utcnow() - timedelta(minutes=30)

latest_subq = (
    db.query(
        PodMetric.pod_name,
        PodMetric.node_name,
        PodMetric.cpu_request_millicores,
        PodMetric.memory_request_bytes,
        PodMetric.cpu_usage_millicores,
        PodMetric.memory_usage_bytes,
    )
    .filter(
        PodMetric.cluster_id == cluster_id,
        PodMetric.timestamp >= _pod_cutoff,
    )
    .distinct(PodMetric.pod_name)
    .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
    .subquery()
)

query = (
    db.query(
        NodeMetadata.node_name,
        func.count(func.distinct(latest_subq.c.pod_name)).label("pod_count")
    )
    .select_from(NodeMetadata)
    .outerjoin(
        latest_subq,
        (NodeMetadata.cluster_id == cluster_id)
        & (NodeMetadata.node_name == latest_subq.c.node_name)
    )
    .filter(NodeMetadata.cluster_id == cluster_id)
    .group_by(
        NodeMetadata.node_name
    )
)

print(query)
rows = query.all()
print(f"Total rows: {len(rows)}")
for r in rows:
    print(r.node_name)
