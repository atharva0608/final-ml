import sys
sys.path.insert(0, '/Users/atharvapudale/Desktop/backend-ecc/Atharva Repo/github/final-ml')
from backend.db.session import SessionLocal
from backend.models.pod_metric import PodMetric
from sqlalchemy import func
from datetime import datetime, timedelta

db = SessionLocal()
cluster_id = "d2fce9ce-405d-4e26-bf9c-9c203d1fbb3f"
_cutoff = datetime.utcnow() - timedelta(minutes=3)

_distinct_pods_sub = (
    db.query(
        PodMetric.pod_name,
        PodMetric.cpu_request_millicores,
    )
    .filter(
        PodMetric.cluster_id == cluster_id,
        PodMetric.controller_kind != "DaemonSet",
        ~PodMetric.namespace.in_(["kube-system", "kube-public", "kube-node-lease"]),
        (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
        PodMetric.timestamp > _cutoff,
    )
    .distinct(PodMetric.pod_name)
    .subquery()
)

_cpu_demand_rows = db.query(func.sum(_distinct_pods_sub.c.cpu_request_millicores)).scalar()

print(f"Total CPU demand: {_cpu_demand_rows}")

alloc_cpu_total = 0
from backend.models.node_metadata import NodeMetadata
for nr in db.query(NodeMetadata).filter(NodeMetadata.cluster_id == cluster_id).all():
    print(f"Node: {nr.node_name}, alloc: {nr.allocatable_cpu_millicores}")
    alloc_cpu_total += int((nr.allocatable_cpu_millicores or 4000)*0.85)
    
print(f"Total Effective Allocatable CPU (85%): {alloc_cpu_total}")
