from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from backend.models.base import get_db
from backend.models.user import User
from backend.models.cluster import Cluster
from backend.models.account import Account
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
    InstallScriptResponse,
    UnifiedOptimizationSettings
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

@router.patch("/{cluster_id}/auto-rebalance")
def toggle_auto_rebalance(
    cluster_id: str,
    enabled: bool = Query(..., description="Enable or disable auto-rebalancing"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle automatic on-demand → spot rebalancing for a cluster.

    When enabled, the system will automatically create rebalancing actions
    to migrate on-demand instances to spot instances for cost savings.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Update auto-rebalance setting
    cluster.auto_rebalance_enabled = enabled
    db.commit()
    db.refresh(cluster)

    logger.info(f"Auto-rebalance {'enabled' if enabled else 'disabled'} for cluster {cluster_id} by user {current_user.email}")

    return {
        "cluster_id": cluster_id,
        "auto_rebalance_enabled": cluster.auto_rebalance_enabled,
        "status": "success",
        "message": f"Auto-rebalancing {'enabled' if enabled else 'disabled'}"
    }

@router.delete("/{cluster_id}")
def delete_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service),
    db: Session = Depends(get_db)
):
    """
    Delete a cluster and clean up all associated AWS + Kubernetes resources.
    Cleanup is best-effort — DB row is deleted even if AWS cleanup partially fails.
    """
    from backend.services.cluster_cleanup_service import ClusterCleanupService

    # Load cluster before deletion so we have name/region for cleanup
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        return {"status": "success", "message": "Cluster already deleted"}

    cleanup_results = {}
    try:
        account = db.query(Account).filter(Account.id == cluster.account_id).first()
        if account and account.role_arn:
            from backend.services.agent_injector import AgentInjectorService
            _inj = AgentInjectorService(db)
            try:
                # Use existing _assume_role to get temporary credentials for cleanup
                _creds = _inj._assume_role(
                    role_arn=account.role_arn,
                    external_id=account.external_id or "",
                    region=cluster.region or "ap-south-1",
                )
                import boto3 as _boto3
                boto_session = _boto3.Session(
                    aws_access_key_id=_creds["access_key"],
                    aws_secret_access_key=_creds["secret_key"],
                    aws_session_token=_creds.get("session_token"),
                    region_name=cluster.region or "ap-south-1",
                )
                k8s_reachable = cluster.agent_installed == "Y"
                cleanup_svc = ClusterCleanupService()
                cleanup_results = cleanup_svc.cleanup_cluster(
                    cluster=cluster,
                    account=account,
                    boto_session=boto_session,
                    db=db,
                    k8s_reachable=k8s_reachable,
                )
                logger.info(f"Cluster {cluster_id} AWS/K8s cleanup: {cleanup_results}")
            except Exception as cleanup_err:
                logger.warning(f"Cluster {cluster_id} cleanup partial failure (non-blocking): {cleanup_err}")
    except Exception as e:
        logger.warning(f"Cluster {cluster_id} cleanup skipped — no account credentials: {e}")

    # Soft-delete: mark as dismissed so discovery won't re-add it
    try:
        from backend.models.cluster import ClusterStatus as _CS
        cluster.is_dismissed = True
        # Use INACTIVE for soft-delete marker; some deployed DBs don't include
        # TERMINATED in the clusterstatus enum yet.
        cluster.status = _CS.INACTIVE
        db.commit()

        # BUG-5 fix: Clean up Redis keys scoped to this cluster.
        # Keys with short TTLs self-expire; only clean long-lived / no-TTL keys.
        try:
            from backend.core.redis_client import get_redis_client as _grc_b5
            _r = _grc_b5()
            _direct_keys = [
                f"cluster_pools:{cluster_id}",
                f"rebalance:lock:{cluster_id}",
                f"spot:stabilization_lock:{cluster_id}",
                f"spot:daily_count:{cluster_id}",
                f"spot:last_check:{cluster_id}",
                f"rebalance:active_count:{cluster_id}",
                f"karpenter_config:{cluster_id}",
            ]
            for _dk in _direct_keys:
                try:
                    _r.delete(_dk)
                except Exception:
                    pass
            # Scan-delete wildcard patterns (launch_blocked, cooldown, etc.)
            for _pattern in [
                f"spot:launch_blocked:{cluster_id}:*",
                f"spot:cooldown:*:{cluster_id}",
                f"lock:node_action:{cluster_id}:*",
            ]:
                try:
                    _cursor = 0
                    while True:
                        _cursor, _keys = _r.scan(_cursor, match=_pattern, count=100)
                        if _keys:
                            _r.delete(*_keys)
                        if _cursor == 0:
                            break
                except Exception:
                    pass
            logger.info(f"Cleared Redis keys for deleted cluster {cluster_id}")
        except Exception as _redis_err:
            logger.warning(f"Redis cleanup for cluster {cluster_id} failed (non-blocking): {_redis_err}")

        logger.info(f"Cluster {cluster_id} ({cluster.name}) dismissed by {current_user.email}")
        return {"status": "success", "message": "Cluster removed", "cleanup": cleanup_results}
    except Exception as e:
        logger.error(f"Cluster {cluster_id} dismiss failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cluster removal failed: {str(e)}")

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
        
        # Always sync api_key to AGENT_API_KEY env var so verify_agent_token()
        # accepts the agent's Bearer token.  Using a stale random key is the
        # root cause of 401 CrashLoopBackOff on every reinstall.
        import os as _os
        _backend_key = _os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
        if cluster.api_key != _backend_key:
            cluster.api_key = _backend_key
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


@router.post("/{cluster_id}/update-agent")
def update_agent(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an already-installed agent — idempotently re-deploys DaemonSet + Orchestrator Deployment.
    Use this to add the Orchestrator Deployment to clusters that only have the DaemonSet.
    """
    from backend.services.agent_injector import AgentInjectorService
    from backend.models.cluster import Cluster
    from backend.models.account import Account

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    if not cluster.api_key:
        raise HTTPException(status_code=400, detail="Cluster has no API key — install agent first")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account or not account.role_arn:
        raise HTTPException(status_code=400, detail="No role ARN found for this cluster's account")

    from backend.workers.tasks.agent_tasks import inject_agent_task
    task = inject_agent_task.delay(cluster_id=cluster.id)

    return {
        "status": "accepted",
        "message": "Agent update (DaemonSet + Orchestrator) started in background",
        "task_id": str(task.id)
    }


@router.post("/{cluster_id}/fallback")
def request_fallback_node(
    cluster_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Handle Spot Interruption Fallback Request.

    Triggered by the Agent when it receives a spot termination notice (2-minute warning)
    for a node in this cluster.  Immediately switches the Karpenter NodePool to on-demand
    so any replacement nodes provisioned by Karpenter use on-demand capacity instead of
    continuing to target the same interrupted spot pool.

    Payload fields:
        node_name (str):          K8s node name of the interrupting node
        reason    (str):          e.g. "spot_interruption" | "rebalance_notice"
        instance_type (str, opt): EC2 instance type that was interrupted
        az        (str, opt):     AZ of the interrupting node
    """
    from backend.services.karpenter_service import KarpenterService
    from backend.models.cluster import Cluster
    from backend.models.node_template import NodeTemplate
    import logging
    import re as _re
    logger = logging.getLogger("api")

    def _sanitize_log(value, max_len: int = 100) -> str:
        """BUG-16 fix: strip control characters and limit length for safe logging."""
        if not isinstance(value, str):
            return str(value)[:max_len] if value is not None else ""
        return _re.sub(r'[\x00-\x1f\x7f]', '_', value)[:max_len]

    node_name     = _sanitize_log(payload.get("node_name"))
    reason        = _sanitize_log(payload.get("reason", "spot_interruption"))
    instance_type = _sanitize_log(payload.get("instance_type"))
    az            = _sanitize_log(payload.get("az"))

    logger.critical(
        "[FALLBACK] Spot interruption received — cluster=%s node=%s instance=%s az=%s reason=%s",
        cluster_id, node_name, instance_type, az, reason
    )

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        # Fetch the node template to get the allowed instance types and AZs
        # (KarpenterService.switch_to_ondemand needs them to build the NodePool spec)
        template = None
        if cluster.node_template_id:
            template = db.query(NodeTemplate).filter(
                NodeTemplate.id == cluster.node_template_id
            ).first()

        template_instance_types = (
            template.instance_types if template and template.instance_types
            else ["m5.large", "m5.xlarge", "m6i.large", "m6i.xlarge", "c5.large"]
        )
        template_azs = (
            template.availability_zones if template and getattr(template, "availability_zones", None)
            else None
        )

        karpenter_svc = KarpenterService(db)
        result = karpenter_svc.switch_to_ondemand(
            cluster_id=cluster_id,
            template_instance_types=template_instance_types,
            template_azs=template_azs,
            nodepool_name="default",
        )

        logger.info(f"[FALLBACK] switch_to_ondemand result: {result}")
        return {
            "status":  "success",
            "message": "NodePool switched to on-demand — Karpenter will provision OD replacement",
            "action":  "SWITCH_NODEPOOL_TO_ONDEMAND",
            "node":    node_name,
            "result":  result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FALLBACK] Failed to switch to on-demand for cluster {cluster_id}: {e}", exc_info=True)
        # Return success with degraded message so the agent doesn't retry in a loop
        return {
            "status":  "degraded",
            "message": f"Fallback attempted but NodePool switch failed: {str(e)[:200]}",
            "action":  "LAUNCH_ON_DEMAND",
        }

@router.get("/{cluster_id}/utilization")
def get_cluster_utilization(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get cluster utilization metrics including:
    - CPU utilization (%)
    - Memory utilization (%)
    - Pod count
    - Node count
    - Average resource usage
    """
    try:
        return service.get_cluster_utilization(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{cluster_id}/workload-type")
def get_cluster_workload_type(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get cluster workload type (STATELESS/STATEFUL/MIXED) based on PVC detection.

    Detection logic:
    - STATELESS: No PVCs attached to any pods
    - STATEFUL: One or more pods have PVCs attached
    - MIXED: Combination of stateless and stateful workloads
    """
    try:
        return service.get_cluster_workload_type(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{cluster_id}/nodes/detailed")
def get_cluster_nodes_detailed(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Get detailed node information including:
    - Node-level utilization (CPU %, Memory %)
    - Instance type, lifecycle (spot/on-demand)
    - List of pods running on each node
    - Pod-level PVC detection
    - Pod controller type (Deployment, StatefulSet, DaemonSet, etc.)
    - Node classification (STATELESS/STATEFUL based on pods)
    """
    try:
        return service.get_cluster_nodes_detailed(cluster_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{cluster_id}/agent/disconnect")
def disconnect_agent(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disconnect the agent from this cluster.

    Rotates the cluster API key so the running DaemonSet can no longer
    authenticate with the backend. All historical data (pod metrics,
    instance records) is PRESERVED — only future data collection stops.

    Use this when you want to pause monitoring without losing history.
    """
    import secrets

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from backend.models.cluster import ClusterStatus
    import os as _os
    # Rotate API key — must equal AGENT_API_KEY env var for verify_agent_token()
    cluster.api_key = _os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
    cluster.agent_installed = "N"
    cluster.status = ClusterStatus.DISCONNECTED
    cluster.updated_at = datetime.utcnow()
    db.commit()

    # Issue #8: Force-close any active WebSocket connection for this cluster
    # so the agent cannot continue sending/receiving commands on the old session.
    try:
        from backend.core import api_gateway
        ws = api_gateway.active_connections.pop(cluster_id, None)
        if ws:
            import asyncio
            try:
                asyncio.get_event_loop().create_task(ws.close(code=1008, reason="API key rotated"))
            except RuntimeError:
                pass  # No event loop — WS will fail on next send anyway
            logger.info(f"Force-closed WebSocket for cluster {cluster_id}")
    except Exception as ws_err:
        logger.warning(f"WebSocket cleanup skipped for {cluster_id}: {ws_err}")

    logger.info(f"Agent disconnected from cluster {cluster_id} by user {current_user.id}")
    return {
        "message": "Agent disconnected. Historical data preserved.",
        "cluster_id": cluster_id,
        "agent_installed": "N"
    }


@router.delete("/{cluster_id}/agent")
def remove_agent(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove the agent and delete ALL associated data for this cluster.

    This permanently:
    - Rotates the API key (agent DaemonSet stops authenticating)
    - Deletes all pod_metrics records for this cluster
    - Deletes all instance records for this cluster
    - Resets cluster status to DISCOVERED (no agent state)
    - Clears last_heartbeat

    The cluster registration itself is kept. Re-install the agent to
    resume data collection from scratch.

    WARNING: This action is irreversible.
    """
    import secrets
    from backend.models.pod_metric import PodMetric
    from backend.models.instance import Instance
    from backend.models.cluster import ClusterStatus

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # ── AWS CLEANUP: delete all Karpenter AWS resources created by platform ──
    # Runs before Kubernetes uninstall so IAM roles aren't deleted while Karpenter is still running.
    _acct = getattr(cluster, 'account', None)
    _aws_role = cluster.aws_role_arn or (_acct.role_arn if _acct else "")
    if _aws_role:
        try:
            from backend.services.agent_injector import AgentInjectorService as _Inj
            _inj = _Inj(db)
            _ext = cluster.aws_external_id or (_acct.external_id if _acct else "")
            _rgn = cluster.region or "ap-south-1"
            _creds = _inj._assume_role(role_arn=_aws_role, external_id=_ext or "", region=_rgn)
            if _creds:
                _result = _inj.delete_all_cluster_karpenter_resources(
                    cluster_name=cluster.name, region=_rgn, credentials=_creds)
                logger.info(
                    f"[remove_agent] AWS cleanup for {cluster.name}: "
                    f"{len(_result.get('deleted', []))} deleted, "
                    f"{len(_result.get('errors', []))} warnings"
                )
        except Exception as _aws_err:
            logger.warning(
                f"[remove_agent] AWS cleanup failed for {cluster.name} (non-fatal): {_aws_err}")

    # Attempt to uninstall DaemonSet from the actual Kubernetes cluster
    if cluster.endpoint and cluster.ca_data and _acct:
        try:
            from backend.services.agent_injector import AgentInjectorService
            injector = AgentInjectorService(db)
            uninstall_result = injector.uninstall_agent(
                cluster_name=cluster.name,
                cluster_endpoint=cluster.endpoint,
                cluster_ca_data=cluster.ca_data,
                role_arn=_acct.role_arn,
                external_id=_acct.external_id,
                region=cluster.region or "us-east-1"
            )
            logger.info(f"K8s agent uninstall for cluster {cluster_id}: {uninstall_result}")
        except Exception as uninstall_err:
            # Log but don't abort — still clean up DB state so UI reflects removal
            logger.warning(f"K8s uninstall failed for cluster {cluster_id}, continuing with DB cleanup: {uninstall_err}")

    # Count records being deleted for the response
    pod_metrics_count = db.query(PodMetric).filter(PodMetric.cluster_id == cluster_id).count()
    instance_count = db.query(Instance).filter(Instance.cluster_id == cluster_id).count()

    # Delete all pod metrics
    db.query(PodMetric).filter(PodMetric.cluster_id == cluster_id).delete(synchronize_session=False)

    # Delete all instances
    db.query(Instance).filter(Instance.cluster_id == cluster_id).delete(synchronize_session=False)

    # Reset cluster state
    cluster.agent_installed = "N"
    cluster.status = ClusterStatus.DISCOVERED
    cluster.last_heartbeat = None
    import os as _os
    cluster.api_key = _os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
    cluster.updated_at = datetime.utcnow()

    db.commit()

    logger.info(
        f"Agent removed from cluster {cluster_id} by user {current_user.id} — "
        f"deleted {pod_metrics_count} pod_metrics, {instance_count} instances"
    )
    return {
        "message": "Agent removed and all data deleted.",
        "cluster_id": cluster_id,
        "cluster_status": "discovered"
    }


@router.get("/{cluster_id}/optimization-settings", response_model=UnifiedOptimizationSettings)
def get_cluster_optimization_settings(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the unified optimization settings for a cluster.
    """
    from backend.models.cluster import Cluster, ClusterOptimizationSettings, OptimizationStrategy, StatelessRuntimeRules, StatefulRules
    
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    automation = cluster.optimization_settings
    strategy = cluster.optimization_strategy_profile
    stateless = cluster.stateless_rules
    stateful = cluster.stateful_rules
    
    return {
        "automation_controls": {
            "auto_rebalance_enabled": automation.auto_rebalance_enabled if automation else False,
            "auto_rightsizing_enabled": automation.auto_rightsizing_enabled if automation else False,
            "instance_aware_rightsizing": automation.instance_aware_rightsizing if automation else False,
            "cooldown_override_minutes": automation.cooldown_override_minutes if automation else None,
            "spot_join_timeout_minutes": automation.spot_join_timeout_minutes if automation else None,
            "manual_approval_required": automation.manual_approval_required if automation else False,
            "target_spot_exposure_pct": automation.target_spot_exposure_pct if automation else 100,
            # Sub-toggles — required so the frontend doesn't overwrite them with stale defaults on save
            "maintain_standby": automation.maintain_standby if automation else False,
            "diversify_pools": automation.diversify_pools if automation else False,
            "max_family_diversification_cap_pct": automation.max_family_diversification_cap_pct if automation else 40,
            "instance_type_diversification_pct": automation.instance_type_diversification_pct if automation else 100,
            "failure_cooldown_minutes": automation.failure_cooldown_minutes if automation else 30,
            "min_node_count": automation.min_node_count if automation else 1,
            "scale_down_threshold_pct": automation.scale_down_threshold_pct if automation else 20,
            "scale_down_stabilization_minutes": automation.scale_down_stabilization_minutes if automation else 15,
            "enable_ascp_auto_scaler": automation.enable_ascp_auto_scaler if automation else False,
            "check_interval_seconds": automation.check_interval_seconds if automation else 15,
            "architecture_preference": automation.architecture_preference if automation else "both",
        },
        "optimization_strategy": {
            "strategy_type": strategy.strategy_type if strategy else "BALANCED",
            "risk_ceiling_percent": strategy.risk_ceiling_percent if strategy else 25,
            "min_savings_percent": strategy.min_savings_percent if strategy else 15,
            "volatility_tolerance_percent": strategy.volatility_tolerance_percent if strategy else 20,
            "migration_penalty_multiplier": strategy.migration_penalty_multiplier if strategy else 1.5,
            "diversity_strictness_level": strategy.diversity_strictness_level if strategy else "Medium",
            "risk_savings_tradeoff_pct": strategy.risk_savings_tradeoff_pct if strategy else 20
        },
        "stateless_rules": {
            "instance_diversification_enabled": stateless.instance_diversification_enabled if stateless else True,
            "respect_pdb_enabled": stateless.respect_pdb_enabled if stateless else True,
            "prewarm_minutes": stateless.prewarm_minutes if stateless else 0,
            "substitute_strategy": stateless.substitute_strategy if stateless else "PREWARMED",
            "max_rebalances_per_24h": stateless.max_rebalances_per_24h if stateless else 5,
            "resize_cooldown_minutes": stateless.resize_cooldown_minutes if stateless else 120,
            "resize_headroom_multiplier": stateless.resize_headroom_multiplier if stateless else 1.2,
            "volatility_safety_multiplier": stateless.volatility_safety_multiplier if stateless else 1.35,
            "fresh_cluster_stabilization_minutes": stateless.fresh_cluster_stabilization_minutes if stateless else 1440
        },
        "stateful_rules": {
            "manual_resize_allowed": stateful.manual_resize_allowed if stateful else True,
            "require_approval": stateful.require_approval if stateful else True,
            "block_spot_for_stateful": stateful.block_spot_for_stateful if stateful else True,
            "max_downscale_percent": stateful.max_downscale_percent if stateful else 25
        }
    }

@router.put("/{cluster_id}/optimization-settings", response_model=UnifiedOptimizationSettings)
def update_cluster_optimization_settings(
    cluster_id: str,
    settings: UnifiedOptimizationSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the unified optimization settings for a cluster.
    """
    from backend.models.cluster import Cluster, ClusterOptimizationSettings, OptimizationStrategy, StatelessRuntimeRules, StatefulRules
    
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    # Automation Controls (partial update — only applied when section is present)
    _diversify_just_enabled = False
    if settings.automation_controls is not None:
        if not cluster.optimization_settings:
            cluster.optimization_settings = ClusterOptimizationSettings(cluster_id=cluster_id)
        _prev_diversify = bool(getattr(cluster.optimization_settings, 'diversify_pools', False))
        for k, v in settings.automation_controls.model_dump().items():
            setattr(cluster.optimization_settings, k, v)
        _new_diversify = bool(getattr(cluster.optimization_settings, 'diversify_pools', False))
        if _new_diversify and not _prev_diversify:
            _diversify_just_enabled = True

    # Optimization Strategy
    if settings.optimization_strategy is not None:
        if not cluster.optimization_strategy_profile:
            cluster.optimization_strategy_profile = OptimizationStrategy(cluster_id=cluster_id)
        for k, v in settings.optimization_strategy.model_dump().items():
            setattr(cluster.optimization_strategy_profile, k, v)

    # Stateless Rules
    if settings.stateless_rules is not None:
        if not cluster.stateless_rules:
            cluster.stateless_rules = StatelessRuntimeRules(cluster_id=cluster_id)
        for k, v in settings.stateless_rules.model_dump().items():
            setattr(cluster.stateless_rules, k, v)

    # Stateful Rules
    if settings.stateful_rules is not None:
        if not cluster.stateful_rules:
            cluster.stateful_rules = StatefulRules(cluster_id=cluster_id)
        for k, v in settings.stateful_rules.model_dump().items():
            setattr(cluster.stateful_rules, k, v)
        
    db.commit()

    # Immediate re-evaluation when Diversify Spot Pools is turned ON.
    # Clear NodePool cooldown + global pool ranking caches so the next
    # auto_rebalancer cycle (≤15s) re-picks diverse pools right away.
    if _diversify_just_enabled:
        try:
            from backend.core.redis_client import get_redis_client as _grc_div
            _redis_div = _grc_div()
            _redis_div.delete(f"spot:karpenter:nodepool_updated:{cluster_id}")
            _cluster_region = cluster.region or "ap-south-1"
            _redis_div.delete(f"global_pool_rankings:{_cluster_region}")
            _redis_div.delete("ascpai:pool_rankings")
        except Exception:
            pass  # Non-fatal — rebalancer will pick up diversity on next natural cycle

    return get_cluster_optimization_settings(cluster_id=cluster_id, current_user=current_user, db=db)


# ── Task 7.2: Unified Cluster Summary Endpoint ──────────────────

@router.get("/{cluster_id}/summary")
def get_cluster_summary(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unified cluster summary endpoint — single call aggregating:
    - Circuit breaker status
    - Optimizer phase and trust phase
    - Pool rotation health
    - Rejection counters (24h)
    - Spend velocity
    - Cooldown status
    """
    from backend.core.redis_client import get_redis_client
    from backend.services.circuit_breaker import CircuitBreaker
    from backend.services.cooldown_controller import CooldownController
    from backend.services.optimizer_coordinator import OptimizerCoordinator
    from backend.core.decision_engine import DecisionEngine

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    redis = get_redis_client()

    # Circuit breaker
    cb = CircuitBreaker(redis)
    cb_status = cb.check_and_auto_recover(cluster_id)

    # Optimizer phase + trust
    coordinator = OptimizerCoordinator(db, redis)
    optimizer_status = coordinator.get_cluster_status(cluster_id)
    trust = coordinator.get_cluster_trust_phase(cluster_id)

    # Pool rotation
    rotation_raw = redis.get(f"spot:pool_rotation_status:{cluster_id}")
    import json
    pool_rotation = json.loads(rotation_raw) if rotation_raw else None

    # Rejection counters (Task 7.1)
    engine = DecisionEngine(redis, db)
    rejection_counters = engine.get_rejection_counters(cluster_id)

    # Cooldown
    cooldown = CooldownController(redis)
    cooldown_status = cooldown.get_action_cooldown_status(cluster_id)
    stabilization_locked, stab_remaining = cooldown.is_stabilization_locked(cluster_id)

    # Spend velocity
    velocity_raw = redis.get(f"spot:spend_velocity:{cluster_id}")
    spend_velocity = float(velocity_raw) if velocity_raw else 0.0

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "region": cluster.region,
        "circuit_breaker": cb_status,
        "optimizer": {
            "phase": optimizer_status.get("phase"),
            "hours_in_phase": optimizer_status.get("hours_in_phase"),
            "can_pool_optimize": optimizer_status.get("can_run_pool_optimization"),
            "can_rightsize": optimizer_status.get("can_run_rightsizing_evaluation"),
            "pending_proposal": optimizer_status.get("pending_proposal"),
        },
        "trust_phase": trust,
        "pool_rotation": pool_rotation,
        "rejection_counters": rejection_counters,
        "cooldown": {
            **cooldown_status,
            "stabilization_locked": stabilization_locked,
            "stabilization_remaining_seconds": stab_remaining,
        },
        "spend_velocity": spend_velocity,
        "is_hibernating": getattr(cluster, 'is_hibernating', False),
    }
