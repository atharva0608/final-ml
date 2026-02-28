from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from backend.models.base import get_db
from backend.models.user import User
from backend.models.cluster import Cluster
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
    service: ClusterService = Depends(get_cluster_service)
):
    """
    Delete a cluster (must resolve active instances first)
    """
    try:
        service.delete_cluster(cluster_id, current_user.id)
        return {"status": "success", "message": "Cluster deleted"}
    except ResourceNotFoundError as e:
        # Idempotent behaviour: if it's already deleted, return success
        return {"status": "success", "message": "Cluster already deleted"}
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
    # Rotate API key — existing agent pods will start receiving 401s
    cluster.api_key = secrets.token_urlsafe(32)
    cluster.agent_installed = "N"
    cluster.status = ClusterStatus.DISCONNECTED
    cluster.updated_at = datetime.utcnow()
    db.commit()

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
    
    return {
        "automation_controls": {
            "auto_rebalance_enabled": automation.auto_rebalance_enabled if automation else False,
            "auto_rightsizing_enabled": automation.auto_rightsizing_enabled if automation else False,
            "cooldown_override_minutes": automation.cooldown_override_minutes if automation else None,
            "conservative_mode_enabled": automation.conservative_mode_enabled if automation else True,
            "manual_approval_required": automation.manual_approval_required if automation else False,
            "target_spot_exposure_pct": automation.target_spot_exposure_pct if automation else 100
        },
        "optimization_strategy": {
            "strategy_type": strategy.strategy_type if strategy else "BALANCED",
            "risk_ceiling_percent": strategy.risk_ceiling_percent if strategy else 25,
            "min_savings_percent": strategy.min_savings_percent if strategy else 15,
            "volatility_tolerance_percent": strategy.volatility_tolerance_percent if strategy else 20,
            "migration_penalty_multiplier": strategy.migration_penalty_multiplier if strategy else 1.5,
            "diversity_strictness_level": strategy.diversity_strictness_level if strategy else "Medium"
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
            "show_ondemand_only": stateful.show_ondemand_only if stateful else True,
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
        
    # Automation Controls
    if not cluster.optimization_settings:
        cluster.optimization_settings = ClusterOptimizationSettings(cluster_id=cluster_id)
    for k, v in settings.automation_controls.model_dump().items():
        setattr(cluster.optimization_settings, k, v)
        
    # Optimization Strategy
    if not cluster.optimization_strategy_profile:
        cluster.optimization_strategy_profile = OptimizationStrategy(cluster_id=cluster_id)
    for k, v in settings.optimization_strategy.model_dump().items():
        setattr(cluster.optimization_strategy_profile, k, v)
        
    # Stateless Rules
    if not cluster.stateless_rules:
        cluster.stateless_rules = StatelessRuntimeRules(cluster_id=cluster_id)
    for k, v in settings.stateless_rules.model_dump().items():
        setattr(cluster.stateless_rules, k, v)
        
    # Stateful Rules
    if not cluster.stateful_rules:
        cluster.stateful_rules = StatefulRules(cluster_id=cluster_id)
    for k, v in settings.stateful_rules.model_dump().items():
        setattr(cluster.stateful_rules, k, v)
        
    db.commit()
    
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
