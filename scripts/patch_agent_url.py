"""Patch agent DaemonSet and orchestrator Deployment in EKS to use ngrok backend URL.
Handles env vars that use valueFrom by clearing the ref when setting value directly."""
import sys
import os
sys.path.insert(0, '/app')
os.chdir('/app')

from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.services.karpenter_service import KarpenterService
from kubernetes import client

CLUSTER_ID = 'a91bec43-4c5a-48dd-aea7-92a644a1a48a'
NGROK_URL = 'https://geophytic-personably-gale.ngrok-free.dev'
NGROK_WS_URL = 'wss://geophytic-personably-gale.ngrok-free.dev/ws'

db = next(get_db())
cluster = db.query(Cluster).filter(Cluster.id == CLUSTER_ID).first()
svc = KarpenterService(db=db)
k8s = svc._get_k8s_client(cluster)
apps_v1 = client.AppsV1Api(k8s)
NS = 'spot-optimizer'

def patch_env(container_spec, env_name, env_value):
    """Update or add an env var. Clears valueFrom if present."""
    if container_spec.env is None:
        container_spec.env = []
    for e in container_spec.env:
        if e.name == env_name:
            e.value = env_value
            e.value_from = None
            return
    container_spec.env.append(client.V1EnvVar(name=env_name, value=env_value))

def show_env(containers):
    for c in containers:
        print(f"  Container: {c.name}")
        for e in (c.env or []):
            if 'BACKEND' in (e.name or '') or 'API_KEY' in (e.name or '') or 'CLUSTER' in (e.name or ''):
                src = f"value={e.value}" if e.value else f"valueFrom={e.value_from}"
                print(f"    {e.name}: {src}")

# 1. Patch DaemonSet spot-agent
try:
    ds = apps_v1.read_namespaced_daemon_set('spot-agent', NS)
    print("BEFORE patching DaemonSet spot-agent:")
    show_env(ds.spec.template.spec.containers)
    for c in ds.spec.template.spec.containers:
        patch_env(c, 'BACKEND_URL', NGROK_URL)
        patch_env(c, 'BACKEND_WS_URL', NGROK_WS_URL)
    apps_v1.replace_namespaced_daemon_set('spot-agent', NS, ds)
    print(f"\nPatched DaemonSet spot-agent: BACKEND_URL={NGROK_URL}")
except Exception as e:
    print(f"Failed to patch DaemonSet: {e}")

# 2. Patch Deployment spot-orchestrator
try:
    dep = apps_v1.read_namespaced_deployment('spot-orchestrator', NS)
    print("\nBEFORE patching Deployment spot-orchestrator:")
    show_env(dep.spec.template.spec.containers)
    for c in dep.spec.template.spec.containers:
        patch_env(c, 'BACKEND_URL', NGROK_URL)
        patch_env(c, 'BACKEND_WS_URL', NGROK_WS_URL)
    apps_v1.replace_namespaced_deployment('spot-orchestrator', NS, dep)
    print(f"\nPatched Deployment spot-orchestrator: BACKEND_URL={NGROK_URL}")
except Exception as e:
    print(f"Failed to patch Deployment: {e}")

db.close()
print("\nDone. Agent pods will roll out with new URLs.")
