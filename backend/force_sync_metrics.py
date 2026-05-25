import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.core.redis_client import get_redis_client
from backend.models.pod_metric import PodMetric
from backend.models.node_metadata import NodeMetadata
from backend.redis_keys import (
    agent_data_pod_metrics_key,
    agent_data_cluster_spot_summary_key,
    agent_data_hpa_pdb_key
)

def sync(cluster_id):
    db = SessionLocal()
    redis = get_redis_client()
    
    # 1. Summarize Pod Metrics (Spot vs OD)
    _pod_cutoff = datetime.utcnow() - timedelta(minutes=30)
    
    # Get nodes to know capacity type
    nodes = db.query(NodeMetadata).filter(NodeMetadata.cluster_id == cluster_id).all()
    node_cap_map = {n.node_name: n.capacity_type for n in nodes}
    
    pods = db.query(PodMetric).filter(
        PodMetric.cluster_id == cluster_id,
        PodMetric.timestamp >= _pod_cutoff
    ).all()
    
    # workload_id -> {spot_pods, od_pods, total_pods}
    workload_summary = {}
    hpa_pdb_summary = {}
    for p in pods:
        wid = f"{p.namespace}/{p.controller_name}"
        if wid not in workload_summary:
            workload_summary[wid] = {"spot_pods": 0, "od_pods": 0, "total_pods": 0, "current_cpu_util": 0.0}
            # Dummy HPA/PDB data for demo
            hpa_pdb_summary[wid] = {
                "has_pdb": True,
                "pdb_min_available": 1,
                "hpa_min": 1,
                "hpa_max": 10,
                "has_topology_spread": True,
                "has_pod_anti_affinity": False
            }
        
        cap = (node_cap_map.get(p.node_name) or "ON_DEMAND").upper()
        if "SPOT" in cap:
            workload_summary[wid]["spot_pods"] += 1
        else:
            workload_summary[wid]["od_pods"] += 1
        workload_summary[wid]["total_pods"] += 1

    # 2. Write to Redis
    redis.setex(agent_data_pod_metrics_key(cluster_id), 600, json.dumps(workload_summary))
    redis.setex(agent_data_hpa_pdb_key(cluster_id), 600, json.dumps(hpa_pdb_summary))
    
    # 3. Dummy spot summary
    spot_summary = {
        "total_nodes": len(nodes),
        "spot_nodes": sum(1 for n in nodes if "SPOT" in (n.capacity_type or "").upper()),
        "od_nodes": sum(1 for n in nodes if "SPOT" not in (n.capacity_type or "").upper()),
        "unhealthy_pending_pods": 0
    }
    redis.setex(agent_data_cluster_spot_summary_key(cluster_id), 600, json.dumps(spot_summary))
    
    # 4. Workload states (Legacy/Advisor consumed)
    for wid, data in workload_summary.items():
        state_payload = {
            "ready_replicas": data["total_pods"],
            "current_spot_pods": data["spot_pods"],
            "current_ondemand_pods": data["od_pods"],
            "has_pdb": True,
            "updated_at": datetime.utcnow().timestamp(),
            "pdb_min_available": 1,
            "hpa_min_replicas": 1,
            "hpa_max_replicas": 10
        }
        redis.setex(f"spot:workload:state:{cluster_id}:{wid}", 600, json.dumps(state_payload))

    print(f"Force-synced {len(workload_summary)} workloads (including HPA/PDB) to Redis for {cluster_id}")
    db.close()

if __name__ == "__main__":
    sync('80866378-d9a9-4a4f-a9ca-dfbdf590c9b4')
