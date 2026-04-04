"""Inspect pod_metadata JSONB to determine available scheduling fields."""
from backend.models.base import SessionLocal
from backend.models.pod_metric import PodMetric
from datetime import datetime, timedelta
import json

db = SessionLocal()
pods = db.query(PodMetric).filter(
    PodMetric.cluster_id == "de017dad-078b-4953-a9fd-60656ee565e7",
    PodMetric.timestamp >= datetime.utcnow() - timedelta(hours=24)
).limit(5).all()

for p in pods:
    meta = p.pod_metadata or {}
    print(f"--- {p.namespace}/{p.pod_name} ---")
    print(f"  controller: {p.controller_kind}/{p.controller_name}")
    print(f"  cpu_limit: {p.cpu_limit_millicores}, mem_limit: {p.memory_limit_bytes}")
    print(f"  metadata keys: {list(meta.keys())}")
    if meta:
        print(f"  metadata: {json.dumps(meta, default=str)[:600]}")
    print()
db.close()
