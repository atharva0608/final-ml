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
    Also returns current per-account sync health so the UI can surface
    AccessDenied / credential errors without waiting for the async task.
    """
    from backend.models.account import Account as _Acct, AccountStatus as _AS, SyncStatus as _SS

    # Snapshot account health BEFORE dispatching (reflects the last completed scan)
    _accounts = db.query(_Acct).filter(
        _Acct.organization_id == current_user.organization_id,
    ).all() if hasattr(current_user, 'organization_id') else []

    account_health = []
    for a in _accounts:
        account_health.append({
            "aws_account_id": a.aws_account_id,
            "account_id": a.id,
            "status": a.status.value if a.status else "unknown",
            "sync_status": a.sync_status.value if a.sync_status else "unknown",
            "sync_error": a.sync_error,
            "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
        })

    failed_accounts = [h for h in account_health if h["sync_status"] == "failed"]

    try:
        from backend.workers.tasks.discovery import discovery_worker_loop
        task = discovery_worker_loop.delay()
        task_id = str(task.id)
    except Exception as e:
        logger.error(f"Failed to trigger discovery: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start discovery: {str(e)}")

    return {
        "status": "accepted",
        "message": "Discovery scan started",
        "task_id": task_id,
        "account_health": account_health,
        "failed_accounts": failed_accounts,
    }

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

    # Karpenter gate: cannot enable auto-rebalancing without Karpenter installed
    if enabled and getattr(cluster, 'karpenter_mode', None) is None:
        raise HTTPException(
            status_code=400,
            detail="Karpenter must be installed before enabling auto-rebalancing. "
                   "Please install Karpenter first from the cluster settings."
        )

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

                # ── Direct K8s cleanup: remove agent + Karpenter from EKS ──
                # Skip K8s cleanup if cluster is already unreachable (deleted/disconnected).
                # Attempting to connect to a gone EKS endpoint hangs indefinitely.
                _dead_statuses_del = {'DISCONNECTED', 'DEGRADED', 'INACTIVE', 'DELETED'}
                _cluster_status_del = cluster.status.value if hasattr(cluster.status, 'value') else str(cluster.status)
                if _cluster_status_del in _dead_statuses_del:
                    cleanup_results["k8s"] = {"skipped": f"cluster is {_cluster_status_del} — K8s already unreachable"}
                    logger.info(f"K8s cleanup skipped for {cluster_id}: cluster is {_cluster_status_del}")
                elif cluster.endpoint and cluster.ca_data:
                    try:
                        _uninstall_result = _inj.uninstall_agent(
                            cluster_name=cluster.name,
                            cluster_endpoint=cluster.endpoint,
                            cluster_ca_data=cluster.ca_data,
                            role_arn=account.role_arn,
                            external_id=account.external_id or "",
                            region=cluster.region or "ap-south-1",
                            remove_karpenter=True,
                        )
                        cleanup_results["k8s"] = _uninstall_result
                        logger.info(f"Direct K8s cleanup for {cluster_id}: {_uninstall_result}")
                    except Exception as k8s_err:
                        cleanup_results["k8s"] = {"error": str(k8s_err)}
                        logger.warning(f"Direct K8s cleanup failed for {cluster_id}: {k8s_err}")
                else:
                    cleanup_results["k8s"] = {"skipped": "no endpoint/ca_data stored"}

                # ── AWS resource cleanup ──
                k8s_reachable = False  # Already handled above directly
                cleanup_svc = ClusterCleanupService()
                cleanup_results.update(cleanup_svc.cleanup_cluster(
                    cluster=cluster,
                    account=account,
                    boto_session=boto_session,
                    db=db,
                    k8s_reachable=k8s_reachable,
                ))
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
        # Reset Karpenter mode so re-created clusters don't inherit stale state
        cluster.karpenter_mode = None
        cluster.agent_installed = "N"
        db.commit()

        # Hard-delete child rows that reference this cluster (cascade may not fire
        # on soft-delete). Best-effort — failures won't block cluster removal.
        try:
            from backend.models.pod_metric import PodMetric
            from backend.models.instance import Instance
            from backend.models.agent_action import AgentAction
            from backend.models.rebalancing import RebalancingAction
            db.query(PodMetric).filter(PodMetric.cluster_id == cluster_id).delete(synchronize_session=False)
            db.query(Instance).filter(Instance.cluster_id == cluster_id).delete(synchronize_session=False)
            db.query(AgentAction).filter(AgentAction.cluster_id == cluster_id).delete(synchronize_session=False)
            db.query(RebalancingAction).filter(RebalancingAction.cluster_id == cluster_id).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Hard-deleted child rows for cluster {cluster_id}")
        except Exception as _child_err:
            logger.warning(f"Child row cleanup for {cluster_id} partial failure: {_child_err}")
            db.rollback()

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
                # Karpenter detection keys (prevent stale status on re-created clusters)
                f"karpenter:live_status:{cluster_id}",
                f"karpenter:detected:{cluster_id}",
                f"spot:karpenter:installed:{cluster_id}",
                # Additional cluster state keys
                f"spot:cluster_state:{cluster_id}",
                f"spot:cluster_mode:{cluster_id}",
                f"spot:execution_plan:{cluster_id}",
                f"spot:node_classification:{cluster_id}",
                f"spot:node_arch_constraints:{cluster_id}",
                f"spot:ondemand_fallback:{cluster_id}",
                f"spot:execution_failures:{cluster_id}",
                f"spot:substitute:state:{cluster_id}",
                f"spot:substitute:meta:{cluster_id}",
                f"obs:decisions:{cluster_id}",
                f"cb:state:{cluster_id}",
                f"cb:rollbacks:{cluster_id}",
                f"cb:last_failure:{cluster_id}",
                f"cb:state_entered:{cluster_id}",
                f"metrics:cluster:{cluster_id}:summary",
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
                f"spot:rejection_counter:{cluster_id}:*",
                f"hibernation:lock:*:{cluster_id}",
                f"spot:karpenter:nodepool_updated:{cluster_id}",
                f"spot:warm_spare:*:{cluster_id}",
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
        
        # Ensure the cluster has a stable api_key.
        # Priority:
        #   1. AGENT_API_KEY env var (set in production for single-key deployments)
        #   2. Existing cluster.api_key (preserve across reinstalls — changing it
        #      would CrashLoopBackOff the already-running agent)
        #   3. Generate a fresh token only when the cluster has NO key at all.
        import os as _os
        _env_key = _os.getenv("AGENT_API_KEY")
        if _env_key:
            # Production: enforce global env key so all clusters share one secret
            if cluster.api_key != _env_key:
                cluster.api_key = _env_key
                db.commit()
        elif not cluster.api_key:
            # No env key and no existing key — generate one and persist it
            cluster.api_key = secrets.token_urlsafe(32)
            db.commit()
        # else: cluster already has its own key — leave it alone
        
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
    # Rotate to a fresh random key so the old agent is definitively blocked.
    # We do NOT use AGENT_API_KEY here — that env var is a global shared key and
    # overwriting cluster.api_key with it would break per-cluster isolation.
    # verify_agent_token() now validates per-cluster from the DB, so any unique
    # random value stored here is the single source of truth for this cluster.
    cluster.api_key = secrets.token_urlsafe(32)
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
    # Rotate to a fresh random key — definitively invalidates any still-running
    # agent pod. Next reinstall will pick up a new key from auto_install_agent.
    cluster.api_key = secrets.token_urlsafe(32)
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

    # Compute PDB-safe batch percentage (cached in Redis, 5-min TTL)
    pdb_safe_percent = None
    try:
        from backend.services.pdb_service import get_pdb_safe_percent_for_cluster
        pdb_safe_percent = get_pdb_safe_percent_for_cluster(cluster, db)
    except Exception:
        pass  # Non-critical — UI will use default
    
    return {
        "automation_controls": {
            "auto_rebalance_enabled": automation.auto_rebalance_enabled if automation else False,
            "auto_rightsizing_enabled": automation.auto_rightsizing_enabled if automation else False,
            "instance_aware_rightsizing": automation.instance_aware_rightsizing if automation else False,
            "cooldown_override_minutes": automation.cooldown_override_minutes if automation else None,
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
            "rebalance_batch_percent": automation.rebalance_batch_percent if automation else None,
            "karpenter_only_mode": automation.karpenter_only_mode if automation else False,
            "min_topology_spread": automation.min_topology_spread if automation else 1,
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
        },
        "pdb_safe_percent": pdb_safe_percent,
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

    # Karpenter gate: cannot ENABLE auto-rebalancing or rightsizing without Karpenter.
    # Only fires on False→True transitions, not when re-saving an already-enabled toggle.
    if settings.automation_controls is not None:
        _ac = settings.automation_controls.model_dump()
        # Primary: DB column (set by formal install flow)
        _karpenter_installed = getattr(cluster, 'karpenter_mode', None) is not None
        # Secondary: Redis authoritative keys (set by agent heartbeat / live K8s detection)
        if not _karpenter_installed:
            try:
                from backend.core.redis_client import get_redis_client as _grc_karp_gate
                _kr_gate = _grc_karp_gate()
                if (
                    _kr_gate.exists(f"spot:karpenter:installed:{cluster_id}")
                    or _kr_gate.exists(f"spot:karpenter_auth_verified:{cluster_id}")
                    or _kr_gate.exists(f"karpenter:detected:{cluster_id}")
                ):
                    _karpenter_installed = True
            except Exception:
                pass
        if not _karpenter_installed:
            # Current values in DB (None means not yet configured → treat as False)
            _prev_opt = cluster.optimization_settings
            _prev_rebalance = bool(getattr(_prev_opt, 'auto_rebalance_enabled', False)) if _prev_opt else False
            _prev_rightsizing = bool(getattr(_prev_opt, 'auto_rightsizing_enabled', False)) if _prev_opt else False
            # Only block when turning ON, not when preserving an existing True value
            if _ac.get('auto_rebalance_enabled') and not _prev_rebalance:
                raise HTTPException(
                    status_code=400,
                    detail="Karpenter must be installed before enabling auto-rebalancing. Install Karpenter from the cluster setup page first."
                )
            if _ac.get('auto_rightsizing_enabled') and not _prev_rightsizing:
                raise HTTPException(
                    status_code=400,
                    detail="Karpenter must be installed before enabling auto-rightsizing. Install Karpenter from the cluster setup page first."
                )

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


# ── Migration Endpoints ────────────────────────────────────────────────────────

@router.post("/{cluster_id}/start-migration")
def start_full_migration(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start full migration from managed node groups to Karpenter.

    Pre-checks:
    - Karpenter must be installed (karpenter_mode is not NULL).
    - Agent must be healthy.

    Actions:
    - Sets auto_rebalance_enabled = True
    - Sets target_spot_exposure_pct = 100
    - Sets karpenter_mode = 'auto'
    """
    from backend.models.cluster import Cluster, ClusterOptimizationSettings, KarpenterMode

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Check Karpenter is installed
    if cluster.karpenter_mode is None:
        # Also try Redis detection
        try:
            from backend.core.redis_client import get_redis_client
            redis = get_redis_client()
            karpenter_key = redis.get(f"spot:karpenter:installed:{cluster_id}")
            if not karpenter_key:
                raise HTTPException(
                    status_code=400,
                    detail="Karpenter is not installed on this cluster. Install Karpenter first."
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Karpenter is not installed on this cluster. Install Karpenter first."
            )

    # Already migrated?
    if getattr(cluster, 'managed_node_group_deleted', False):
        raise HTTPException(
            status_code=400,
            detail="Migration already completed — managed node group has been deleted."
        )

    # Enable auto-rebalancing with full migration settings
    opt = db.query(ClusterOptimizationSettings).filter(
        ClusterOptimizationSettings.cluster_id == cluster_id
    ).first()
    if not opt:
        opt = ClusterOptimizationSettings(cluster_id=cluster_id)
        db.add(opt)

    opt.auto_rebalance_enabled = True
    opt.target_spot_exposure_pct = 100
    cluster.auto_rebalance_enabled = True
    cluster.karpenter_mode = KarpenterMode.AUTO

    db.commit()

    return {
        "status": "migration_started",
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "settings": {
            "auto_rebalance_enabled": True,
            "target_spot_exposure_pct": 100,
            "karpenter_mode": "auto",
        },
        "message": f"Full migration started for cluster {cluster.name}. "
                   f"The rebalancer will replace all On-Demand nodes with Spot instances."
    }


@router.get("/{cluster_id}/migration-status")
def get_migration_status(
    cluster_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    §15 — Get stateful migration status for a cluster.

    Returns two things:
    - `active`: any controllers currently being frozen/migrated (from Redis)
    - `history`: recent state-transition events from the migration_event table
    - `node_summary`: spot/on-demand node counts (legacy fields kept for compatibility)
    """
    from backend.models.cluster import Cluster, ClusterOptimizationSettings
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.migration_event import MigrationEvent
    import json
    import redis as _redis_mod

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # ── Legacy node counts (kept for backward-compat) ─────────────────────────
    total_running = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
    ).count()
    od_running = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
        Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
    ).count()
    spot_running = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
        Instance.lifecycle == InstanceLifecycle.SPOT,
    ).count()

    opt = cluster.optimization_settings
    karpenter_only = getattr(opt, 'karpenter_only_mode', False) if opt else False
    managed_ng_deleted = getattr(cluster, 'managed_node_group_deleted', False)
    spot_pct = round(spot_running / total_running * 100, 1) if total_running > 0 else 0.0
    if managed_ng_deleted and karpenter_only:
        phase = "completed"
    elif od_running == 0 and spot_running > 0:
        phase = "completing"
    elif getattr(opt, 'auto_rebalance_enabled', False):
        phase = "in_progress"
    else:
        phase = "not_started"

    # ── Active migrations from Redis (real-time) ──────────────────────────────
    active_migrations = []
    try:
        _redis_url = __import__("os").getenv("REDIS_URL", "redis://localhost:6379/0")
        _rc = _redis_mod.from_url(_redis_url, decode_responses=True)
        _cursor = 0
        _freeze_prefix = f"spot:autoscaler_freeze:"
        while True:
            _cursor, _keys = _rc.scan(_cursor, match=f"{_freeze_prefix}*", count=100)
            for _k in _keys:
                try:
                    _raw = _rc.get(_k)
                    if not _raw:
                        continue
                    _state = json.loads(_raw)
                    _ttl = _rc.ttl(_k)
                    active_migrations.append({
                        "namespace":       _state.get("namespace"),
                        "controller_name": _state.get("controller_name"),
                        "frozen_at":       _state.get("frozen_at"),
                        "hpa_frozen":      _state.get("hpa_frozen", False),
                        "keda_frozen":     _state.get("keda_frozen", False),
                        "ttl_remaining_s": _ttl,
                    })
                except Exception:
                    continue
            if _cursor == 0:
                break
    except Exception:
        pass  # Redis unavailable — return empty active list

    # ── Historical events from migration_event table ───────────────────────────
    try:
        _cluster_int_id = int(cluster_id)
    except (ValueError, TypeError):
        _cluster_int_id = None

    history = []
    if _cluster_int_id is not None:
        events = (
            db.query(MigrationEvent)
            .filter(MigrationEvent.cluster_id == _cluster_int_id)
            .order_by(MigrationEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        for ev in events:
            history.append({
                "id":              ev.id,
                "namespace":       ev.namespace,
                "controller_name": ev.controller_name,
                "controller_kind": ev.controller_kind,
                "workload_tier":   ev.workload_tier,
                "source_node":     ev.source_node,
                "target_node":     ev.target_node,
                "state":           ev.state,
                "failure_reason":  ev.failure_reason,
                "pod_location":    ev.pod_location,
                "freeze_restored": ev.freeze_restored,
                "created_at":      ev.created_at.isoformat() if ev.created_at else None,
            })

    return {
        "cluster_id":             cluster_id,
        "cluster_name":           cluster.name,
        # Legacy fields
        "phase":                  phase,
        "total_nodes":            total_running,
        "on_demand_remaining":    od_running,
        "spot_nodes":             spot_running,
        "spot_percentage":        spot_pct,
        "managed_node_group_deleted": managed_ng_deleted,
        "karpenter_only_mode":    karpenter_only,
        # New §15 fields
        "active_migrations":      active_migrations,
        "history":                history,
    }


@router.post("/{cluster_id}/force-complete-migration")
def force_complete_migration(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Force-complete migration: set karpenter_only_mode=True.

    Safety hatch for when migration is stuck (e.g., PDB-blocked nodes).
    Does NOT delete the managed node group — that must be done manually.
    """
    from backend.models.cluster import Cluster, ClusterOptimizationSettings
    from datetime import datetime

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    opt = db.query(ClusterOptimizationSettings).filter(
        ClusterOptimizationSettings.cluster_id == cluster_id
    ).first()
    if not opt:
        opt = ClusterOptimizationSettings(cluster_id=cluster_id)
        db.add(opt)

    opt.karpenter_only_mode = True
    opt.updated_at = datetime.utcnow()
    cluster.managed_node_group_deleted = True
    cluster.updated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "force_completed",
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "karpenter_only_mode": True,
        "managed_node_group_deleted": True,
        "message": f"Migration force-completed for cluster {cluster.name}. "
                   f"All ASG code paths will be skipped."
    }


# ── W3.6: Anchored Node Status ─────────────────────────────────────────────────


@router.get("/{cluster_id}/anchored-status")
def get_anchored_status(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the list of anchored nodes and their fill ratios for a cluster.

    Anchored nodes are designated on-demand nodes that TIER_0/TIER_1
    workloads are scheduled onto, protected from Karpenter consolidation.
    """
    try:
        from backend.services.anchored_node_service import AnchoredNodeService
        from backend.core.redis_client import get_redis_client
        redis = get_redis_client()
        svc = AnchoredNodeService(db=db, redis=redis)
        anchored_nodes = svc.get_anchored_nodes(cluster_id)
        fill_status = svc.get_anchored_fill_status(cluster_id)
        return {
            "cluster_id":     cluster_id,
            "anchored_nodes": anchored_nodes,
            "node_count":     len(anchored_nodes),
            "fill_status":    fill_status,
        }
    except Exception as e:
        logger.error(f"[cluster_routes] anchored-status failed for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{cluster_id}/anchored-nodes/{node_name}")
def nominate_anchored_node(
    cluster_id: str,
    node_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Nominate a node as an anchored (on-demand protected) node for TIER_1 workloads."""
    try:
        from backend.services.anchored_node_service import AnchoredNodeService
        from backend.core.redis_client import get_redis_client
        redis = get_redis_client()
        svc = AnchoredNodeService(db=db, redis=redis)
        success = svc.nominate_anchored_node(cluster_id, node_name)
        return {
            "success":    success,
            "cluster_id": cluster_id,
            "node_name":  node_name,
            "message":    "Node nominated as anchored" if success else "Node already anchored",
        }
    except Exception as e:
        logger.error(f"[cluster_routes] nominate_anchored_node failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── WorkloadTierPanel: workload tiers endpoint (§15) ───────────────────────────


@router.get("/{cluster_id}/workload-tiers")
def get_workload_tiers(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return all cached workload tier classifications for a cluster.

    Reads ``spot:workload_tier:{cluster_id}:*`` keys from Redis and returns
    them as a list sorted by tier ascending (most critical first).

    Data source: written by ``WorkloadInspector.build_workload_profile()``
    with each scan cycle (TTL 540s / 9 min).  Refresh with the workload
    scanner if data is stale.
    """
    try:
        from backend.core.redis_client import get_redis_client
        import json as _json
        redis = get_redis_client()

        pattern = f"spot:workload_tier:{cluster_id}:*"
        tiers = []

        cursor = 0
        while True:
            cursor, keys = redis.scan(cursor, match=pattern, count=200)
            for key in keys:
                try:
                    raw = redis.get(key)
                    if not raw:
                        continue
                    data = _json.loads(raw)
                    # Key format: spot:workload_tier:{cid}:{ns}/{ctrl}
                    suffix = key.decode("utf-8") if isinstance(key, bytes) else key
                    ctrl_key = suffix.split(f"spot:workload_tier:{cluster_id}:", 1)[-1]
                    ns, ctrl = ctrl_key.rsplit("/", 1) if "/" in ctrl_key else ("default", ctrl_key)
                    tiers.append({
                        "namespace":             ns,
                        "controller_name":       ctrl,
                        "tier":                  data.get("tier", 4),
                        "tier_name":             data.get("tier_name", "SPOT_ELIGIBLE"),
                        "migration_policy":      data.get("policy", "spot_eligible"),
                        "detected_app_type":     data.get("app_type", "unknown"),
                        "classification_confidence": data.get("confidence", 0.0),
                    })
                except Exception:
                    continue
            if cursor == 0:
                break

        tiers.sort(key=lambda t: t["tier"])
        return {
            "cluster_id":  cluster_id,
            "total_count": len(tiers),
            "tiers":       tiers,
        }
    except Exception as e:
        logger.error(f"[cluster_routes] workload-tiers failed for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── §15: Workload tier-override ────────────────────────────────────────────────

@router.patch("/{cluster_id}/workloads/{namespace}/{controller_name}/tier-override")
def patch_workload_tier_override(
    cluster_id: str,
    namespace: str,
    controller_name: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    §15 — Manually override the tier classification for a workload controller.

    Body params:
      - tier (int, required): 0-4 — new tier override
      - reason (str, optional): human-readable note stored in Redis state
      - annotations (dict, optional): extra K8s annotations to apply via
        ANNOTATE_WORKLOAD AgentAction

    Workflow:
      1. Write override to Redis ``spot:workload_tier:{cid}:{ns}/{ctrl}``
         (TTL=None — override persists until cleared).
      2. Queue an ANNOTATE_WORKLOAD AgentAction so the in-cluster agent
         patches the Deployment/StatefulSet with the tier annotation.

    Returns the new tier state.
    """
    import json
    import redis as _redis_mod
    from backend.models.cluster import Cluster
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # ── Validate ──────────────────────────────────────────────────────────────
    tier = body.get("tier")
    if tier is None or not isinstance(tier, int) or tier not in range(5):
        raise HTTPException(
            status_code=422,
            detail="'tier' must be an integer 0-4",
        )
    reason = body.get("reason", "")
    extra_annotations = body.get("annotations", {})
    if not isinstance(extra_annotations, dict):
        extra_annotations = {}

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    _TIER_NAMES = {
        0: "NEVER_MIGRATE",
        1: "ANCHORED_MANUAL",
        2: "STATEFUL_CAREFUL",
        3: "STATELESS_PREFER_SPOT",
        4: "SPOT_ELIGIBLE",
    }
    tier_name = _TIER_NAMES.get(tier, "UNKNOWN")

    # ── Write Redis override ───────────────────────────────────────────────────
    ctrl_key = f"{namespace}/{controller_name}"
    redis_key = f"spot:workload_tier:{cluster_id}:{ctrl_key}"
    tier_state = {
        "tier":               tier,
        "tier_name":          tier_name,
        "policy":             "manual_override",
        "override_reason":    reason,
        "override_by":        getattr(current_user, "email", str(current_user.id)),
        "override_at":        datetime.utcnow().isoformat(),
        "confidence":         1.0,
        "manual_override":    True,
    }
    try:
        _redis_url = __import__("os").getenv("REDIS_URL", "redis://localhost:6379/0")
        _rc = _redis_mod.from_url(_redis_url, decode_responses=True)
        # No TTL — manual override persists until cleared or overwritten
        _rc.set(redis_key, json.dumps(tier_state))
    except Exception as _re:
        logger.warning(f"[cluster_routes] tier-override Redis write failed: {_re}")
        raise HTTPException(status_code=500, detail="Redis write failed")

    # ── Queue ANNOTATE_WORKLOAD AgentAction ───────────────────────────────────
    annotations_to_apply = {
        "spot-optimizer/workload-tier": str(tier),
        "spot-optimizer/tier-name":     tier_name,
        "spot-optimizer/override-by":   getattr(current_user, "email", ""),
        **extra_annotations,
    }
    agent_action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.ANNOTATE_WORKLOAD,
        status=AgentActionStatus.PENDING,
        payload={
            "namespace":       namespace,
            "controller_name": controller_name,
            "controller_kind": body.get("controller_kind", "Deployment"),
            "annotations":     annotations_to_apply,
        },
    )
    db.add(agent_action)
    db.commit()
    db.refresh(agent_action)

    logger.info(
        f"[cluster_routes] Tier override: cluster={cluster_id} "
        f"ctrl={ctrl_key} tier={tier} ({tier_name}) by "
        f"{getattr(current_user, 'email', current_user.id)}"
    )
    return {
        "cluster_id":      cluster_id,
        "namespace":       namespace,
        "controller_name": controller_name,
        "new_tier":        tier,
        "tier_name":       tier_name,
        "agent_action_id": str(agent_action.id),
        "message":         f"Tier override to {tier_name} applied. Agent will annotate the workload.",
    }
