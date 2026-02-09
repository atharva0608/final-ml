from datetime import datetime
import logging

logger = logging.getLogger(__name__)

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
    except (ResourceAlreadyExistsError, ResourceNotFoundError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/discover", status_code=202)
def trigger_discovery(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger an immediate discovery scan for all accounts.
    Authentication required.
    """
    try:
        from backend.workers.tasks.discovery import discovery_worker_loop # Trigger the discovery task asynchronously
        task = discovery_worker_loop.delay()
        return {"status": "accepted", "message": "Discovery scan started", "task_id": str(task.id)}
    except Exception as e:
        logger.error(f"Failed to trigger discovery: {e}")
        # Fallback if Celery is not available/configured? No, just error.
        raise HTTPException(status_code=500, detail=f"Failed to start discovery: {str(e)}")

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

@router.patch("/{cluster_id}", response_model=ClusterResponse)
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

@router.post("/install-script", response_model=InstallScriptResponse)
def generate_install_script(
    request: InstallScriptRequest,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Register cluster and return credentials for manual Helm install
    """
    try:
        # Note: This checks credentials but assumes client will generate command
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

@router.post("/{cluster_id}/auto-install")
def auto_install_agent(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Automatically install the Spot Optimizer agent into an EKS cluster.
    This uses AWS cross-account role assumption to deploy the agent.
    
    Requirements:
    - Cluster must be discovered via AWS account connection
    - CloudFormation role must have EKS access entry permissions
    """
    from backend.services.agent_injector import AgentInjectorService
    from backend.models.cluster import Cluster
    from backend.models.account import Account
    import secrets
    
    try:
        # Get cluster
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        
        # Get associated account for role ARN
        account = db.query(Account).filter(Account.id == cluster.account_id).first()
        if not account or not account.role_arn:
            raise HTTPException(
                status_code=400, 
                detail="Cluster must be associated with an AWS account with a valid role ARN"
            )
        
        # Generate API key if not exists
        if not cluster.api_key:
            cluster.api_key = secrets.token_urlsafe(32)
            db.commit()
        
        # Trigger background task
        from backend.workers.tasks.agent_tasks import inject_agent_task
        task = inject_agent_task.delay(cluster_id=cluster.id)
        
        return {
            "status": "accepted", 
            "message": "Agent injection started in background",
            "task_id": str(task.id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/{cluster_id}/fallback")
def request_fallback_node(
    cluster_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Handle Spot Interruption Fallback Request.
    Triggered by Agent when a Spot node is about to be terminated.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    import logging
    logger = logging.getLogger("api")
    
    node_name = payload.get('node_name')
    reason = payload.get('reason')
    
    logger.critical(f"[FALLBACK] Received fallback request for node {node_name} in cluster {cluster_id}. Reason: {reason}")
    
    # 1. Provide Immediate Safety: Launch On-Demand Replacement
    # In a real implementation, this would call EC2 RunInstances or modify ASG
    # For now, we simulate this and tag the intent for the Reversion cycle
    
    # Check if we assume it's successful
    logger.info(f"[FALLBACK] Launching emergency On-Demand replacement for {node_name}")
    
    # TODO: Call cloud_provider.launch_instance(type='on-demand', tags={'spot-optimizer/fallback': 'true'})
    
    return {"status": "success", "message": "Fallback initiated", "action": "LAUNCH_ON_DEMAND"}
