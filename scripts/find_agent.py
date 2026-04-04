"""Find and patch agent deployment in EKS cluster to use ngrok backend URL."""
import sys
import os
sys.path.insert(0, '/app')
os.chdir('/app')

from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.services.karpenter_service import KarpenterService
from kubernetes import client

CLUSTER_ID = 'a91bec43-4c5a-48dd-aea7-92a644a1a48a'

db = next(get_db())
cluster = db.query(Cluster).filter(Cluster.id == CLUSTER_ID).first()
svc = KarpenterService(db=db)
k8s = svc._get_k8s_client(cluster)
apps_v1 = client.AppsV1Api(k8s)

# Search all namespaces for agent workloads
core_v1 = client.CoreV1Api(k8s)
namespaces = [ns.metadata.name for ns in core_v1.list_namespace().items]

found = []
for ns in namespaces:
    try:
        ds_list = apps_v1.list_namespaced_daemon_set(ns)
        for ds in ds_list.items:
            name = ds.metadata.name.lower()
            if 'agent' in name or 'spot' in name or 'optimizer' in name:
                envs = []
                for c in (ds.spec.template.spec.containers or []):
                    for e in (c.env or []):
                        if 'BACKEND' in (e.name or ''):
                            envs.append(f"  {e.name}={e.value}")
                print(f"DaemonSet: {ns}/{ds.metadata.name}")
                for ev in envs:
                    print(ev)
                found.append(('daemonset', ns, ds.metadata.name))
    except Exception as ex:
        pass
    try:
        dep_list = apps_v1.list_namespaced_deployment(ns)
        for dep in dep_list.items:
            name = dep.metadata.name.lower()
            if 'agent' in name or 'spot' in name or 'optimizer' in name:
                envs = []
                for c in (dep.spec.template.spec.containers or []):
                    for e in (c.env or []):
                        if 'BACKEND' in (e.name or ''):
                            envs.append(f"  {e.name}={e.value}")
                print(f"Deployment: {ns}/{dep.metadata.name}")
                for ev in envs:
                    print(ev)
                found.append(('deployment', ns, dep.metadata.name))
    except Exception as ex:
        pass

if not found:
    print("No agent workload found. Listing all workloads:")
    for ns in namespaces:
        try:
            for ds in apps_v1.list_namespaced_daemon_set(ns).items:
                print(f"  DS: {ns}/{ds.metadata.name}")
        except: pass
        try:
            for dep in apps_v1.list_namespaced_deployment(ns).items:
                print(f"  Deploy: {ns}/{dep.metadata.name}")
        except: pass

db.close()
