import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.pod_metric import PodMetric
from backend.models.workload_classification import WorkloadClassificationRecord

# Database connection
engine = create_engine("postgresql://postgres:postgres@localhost:5432/spot_optimizer")
Session = sessionmaker(bind=engine)
db = Session()

cluster_id = '80866378-d9a9-4a4f-a9ca-dfbdf590c9b4'
_cutoff = datetime.utcnow() - timedelta(minutes=30)
_SYSTEM_NS = ["kube-system", "kube-public", "kube-node-lease"]

wc_rows = (
    db.query(WorkloadClassificationRecord)
    .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
    .all()
)
_wc_ctrl_names = {
    (wc.workload_id.split("/")[-1] if "/" in wc.workload_id else wc.workload_id)
    for wc in wc_rows
}
print(f"WC CTRL Names: {_wc_ctrl_names}")

batch_pod_rows = (
    db.query(
        PodMetric.pod_name,
        PodMetric.controller_name,
        PodMetric.namespace
    )
    .filter(
        PodMetric.cluster_id == cluster_id,
        PodMetric.controller_name.in_(list(_wc_ctrl_names)),
        PodMetric.controller_kind != "DaemonSet",
        ~PodMetric.namespace.in_(_SYSTEM_NS),
        PodMetric.timestamp > _cutoff,
    )
    .distinct(PodMetric.pod_name)
    .all()
)

print(f"Batch Pod Rows Count: {len(batch_pod_rows)}")
for r in batch_pod_rows[:5]:
    print(f"  {r.pod_name} | {r.controller_name} | {r.namespace}")

db.close()
