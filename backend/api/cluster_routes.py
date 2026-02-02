
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from backend.models.base import get_db
from backend.models.user import User
from backend.services.cluster_service import ClusterService
from backend.core.dependencies import get_current_user

def get_cluster_service(db: Session = Depends(get_db)) -> ClusterService:
    return ClusterService(db)
from backend.schemas.cluster_schemas import (
    ClusterResponse, 
    ClusterList, 
    ClusterCreate, 
    ClusterUpdate, 
    AWSConnectRequest, 
    AgentInstallCommand,
    ClusterFilter,
    InstallScriptRequest,
    InstallScriptResponse
)
from backend.core.exceptions import ResourceNotFoundError, ResourceAlreadyExistsError, ValidationError

router = APIRouter(prefix="/clusters", tags=["clusters"])

@router.get("", response_model=ClusterList)
def list_clusters(
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    status: str = None,
    cluster_type: str = None,
    region: str = None,
    account_id: str = None,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    List all clusters with filtering and pagination
    """
    filters = ClusterFilter(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        cluster_type=cluster_type,
        region=region,
        account_id=account_id
    )
    return service.list_clusters(current_user.id, filters)

@router.post("", response_model=ClusterResponse)
def register_cluster(
    cluster_data: ClusterCreate,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Register a new cluster manually
    """
    try:
        return service.register_cluster(current_user.id, cluster_data)
    except (ResourceAlreadyExistsError, ResourceNotFoundError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/connect", response_model=ClusterResponse)
def connect_aws_cluster(
    connect_data: AWSConnectRequest,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Connect an existing AWS cluster via STS (Agentless)
    """
    try:
        return service.connect_aws_cluster(current_user.id, connect_data)
    except (ResourceAlreadyExistsError, ResourceNotFoundError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agent-manifest")
def get_agent_manifest():
    """
    Public endpoint - Returns the Kubernetes agent manifest YAML
    No authentication required for kubectl to fetch
    """
    from fastapi.responses import Response
    
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spot-optimizer-agent
  namespace: spot-optimizer
  labels:
    app: spot-optimizer-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-optimizer-agent
  template:
    metadata:
      labels:
        app: spot-optimizer-agent
    spec:
      serviceAccountName: spot-optimizer-agent
      containers:
      - name: agent
        image: spotoptimizer/agent:latest
        imagePullPolicy: Always
        env:
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: spot-agent-config
              key: API_KEY
        - name: BACKEND_URL
          valueFrom:
            secretKeyRef:
              name: spot-agent-config
              key: BACKEND_URL
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "100m"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: spot-optimizer-agent
  namespace: spot-optimizer
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spot-optimizer-agent
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "namespaces", "services", "configmaps"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["nodes", "pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spot-optimizer-agent
subjects:
- kind: ServiceAccount
  name: spot-optimizer-agent
  namespace: spot-optimizer
roleRef:
  kind: ClusterRole
  name: spot-optimizer-agent
  apiGroup: rbac.authorization.k8s.io
"""
    
    return Response(
        content=manifest.strip(),
        media_type="text/yaml",
        headers={"Content-Disposition": "inline; filename=agent-manifest.yaml"}
    )

@router.post("/verify/{cluster_id}")
def verify_connection(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Verify cluster connection after agent installation
    """
    try:
        return service.verify_connection(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{cluster_id}", response_model=ClusterResponse)
def get_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get cluster details by ID
    """
    try:
        return service.get_cluster(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/{cluster_id}", response_model=ClusterResponse)
def update_cluster(
    cluster_id: str,
    update_data: ClusterUpdate,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Update cluster details
    """
    try:
        return service.update_cluster(cluster_id, current_user.id, update_data)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/{cluster_id}")
def delete_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Delete a cluster (must resolve active instances first)
    """
    try:
        service.delete_cluster(cluster_id, current_user.id)
        return {"status": "success", "message": "Cluster deleted"}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{cluster_id}/install", response_model=AgentInstallCommand)
def get_install_command(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get Kubernetes Agent installation command and manifest
    """
    try:
        return service.generate_agent_install_command(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/install-script", response_model=InstallScriptResponse)
def generate_install_script(
    request: InstallScriptRequest,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Generate install script for a new cluster
    """
    try:
        return service.generate_install_script_provider(current_user.id, request)
    except Exception as e:
        import traceback
        traceback.print_exc() # Print full stack trace to logs
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{cluster_id}/nodes")
def get_cluster_nodes(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get nodes/instances associated with a cluster
    """
    try:
        return service.get_cluster_nodes(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{cluster_id}/costs")
def update_resource_costs(
    cluster_id: str,
    costs: dict,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Update resource costs for a cluster (CPU, Memory, Storage, Ingress, Egress)
    """
    try:
        return service.update_resource_costs(cluster_id, current_user.id, costs)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
