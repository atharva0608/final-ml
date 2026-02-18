"""
Hibernation Worker (WORK-HIB-01)
Schedule-based cluster hibernation and wake-up management

Runs every 1 minute to check hibernation schedules and trigger sleep/wake actions.
Includes pre-warm logic to boot clusters before scheduled wake time.

Three Strategies:
- NAMESPACE_SLEEP: Scale workloads to 0, let Cluster Autoscaler drain nodes
- NUCLEAR: Scale ASGs to 0 directly (hard shutdown)
- SNAPSHOT_RESTORE: Snapshot EBS volumes, then Nuclear sleep (safe for databases)

Dependencies:
- Celery for task scheduling
- SQLAlchemy for database access
- Boto3 for AWS ASG/EBS operations
- kubernetes client for K8s API operations
- pytz for timezone handling
- Modular strategy implementations from Hibernation_strategy/
"""

import logging
import base64
import tempfile
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pytz
from celery import Task
import boto3
from botocore.config import Config
from botocore.signers import RequestSigner
from botocore.exceptions import ClientError

from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.workers import app
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.models.hibernation_schedule import HibernationSchedule, HibernationStrategy
from backend.models.account import Account
from backend.models.cluster_policy import ClusterPolicy
from backend.models.audit_log import AuditLog, AuditOutcome, ResourceType
from backend.core.redis_client import get_redis_client

# Import modular strategy implementations
from backend.Hibernation_strategy import (
    NamespaceSleepStrategy,
    NuclearStrategy,
    SnapshotRestoreStrategy
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# K8s + AWS Helpers
# ---------------------------------------------------------------------------

def _get_assumed_credentials(account: Account, cluster: Cluster) -> Dict:
    """Assume IAM role and return temporary credentials."""
    from backend.models.base import get_db as _get_db
    from backend.models.system_config import SystemConfig

    db = next(_get_db())

    access_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
    secret_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()

    if access_key and secret_key and access_key.value and secret_key.value:
        sts_client = boto3.client(
            'sts',
            aws_access_key_id=access_key.value,
            aws_secret_access_key=secret_key.value,
            region_name=cluster.region or 'us-east-1'
        )
    else:
        sts_client = boto3.client('sts', region_name=cluster.region or 'us-east-1')

    assumed_role = sts_client.assume_role(
        RoleArn=account.role_arn,
        RoleSessionName=f"SpotOptimizer-Hibernation-{cluster.id[:8]}",
        ExternalId=account.external_id,
        DurationSeconds=3600
    )

    return {
        'access_key': assumed_role['Credentials']['AccessKeyId'],
        'secret_key': assumed_role['Credentials']['SecretAccessKey'],
        'session_token': assumed_role['Credentials']['SessionToken']
    }


def _get_eks_token(cluster_name: str, credentials: Dict, region: str) -> str:
    """Generate a Kubernetes authentication token for EKS (SigV4 presigned URL)."""
    session = boto3.Session(
        aws_access_key_id=credentials['access_key'],
        aws_secret_access_key=credentials['secret_key'],
        aws_session_token=credentials.get('session_token'),
        region_name=region
    )

    sts_client = session.client('sts', region_name=region, config=Config(signature_version='v4'))
    signer = RequestSigner(
        sts_client.meta.service_model.service_id,
        region,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }

    url = signer.generate_presigned_url(
        params, region_name=region, expires_in=60, operation_name=''
    )

    token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(
        url.encode('utf-8')
    ).decode('utf-8').rstrip('=')

    return token


def _get_k8s_clients(cluster: Cluster, credentials: Dict):
    """
    Build K8s API clients from cluster endpoint/CA + AWS credentials.

    Returns:
        Tuple of (CoreV1Api, AppsV1Api, AutoscalingV1Api)
    """
    from kubernetes import client as k8s_client
    from kubernetes.client import Configuration, ApiClient

    token = _get_eks_token(cluster.name, credentials, cluster.region)

    ca_file = tempfile.NamedTemporaryFile(delete=False, suffix='.crt')
    ca_file.write(base64.b64decode(cluster.ca_data))
    ca_file.flush()

    config = Configuration()
    config.host = cluster.endpoint
    config.ssl_ca_cert = ca_file.name
    config.api_key = {"authorization": f"Bearer {token}"}

    api_client = ApiClient(configuration=config)
    core_v1 = k8s_client.CoreV1Api(api_client)
    apps_v1 = k8s_client.AppsV1Api(api_client)
    autoscaling_v1 = k8s_client.AutoscalingV1Api(api_client)

    return core_v1, apps_v1, autoscaling_v1


def _get_asg_client(credentials: Dict, region: str):
    """Create an ASG client from assumed-role credentials."""
    return boto3.client(
        'autoscaling',
        region_name=region,
        aws_access_key_id=credentials['access_key'],
        aws_secret_access_key=credentials['secret_key'],
        aws_session_token=credentials.get('session_token')
    )


def _get_ec2_client(credentials: Dict, region: str):
    """Create an EC2 client from assumed-role credentials."""
    return boto3.client(
        'ec2',
        region_name=region,
        aws_access_key_id=credentials['access_key'],
        aws_secret_access_key=credentials['secret_key'],
        aws_session_token=credentials.get('session_token')
    )


def _get_cluster_asgs(asg_client, cluster_name: str) -> List[Dict]:
    """
    Discover ASGs belonging to a cluster by EKS tag.

    Returns list of {name, min, max, desired} dicts.
    """
    paginator = asg_client.get_paginator('describe_auto_scaling_groups')
    matching = []

    for page in paginator.paginate():
        for asg in page['AutoScalingGroups']:
            tags = {t['Key']: t['Value'] for t in asg.get('Tags', [])}
            if f'kubernetes.io/cluster/{cluster_name}' in tags:
                matching.append({
                    'name': asg['AutoScalingGroupName'],
                    'min': asg['MinSize'],
                    'max': asg['MaxSize'],
                    'desired': asg['DesiredCapacity'],
                })

    # Fallback: try conventional name pattern
    if not matching:
        try:
            resp = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[f"{cluster_name}-node-group"]
            )
            for asg in resp.get('AutoScalingGroups', []):
                matching.append({
                    'name': asg['AutoScalingGroupName'],
                    'min': asg['MinSize'],
                    'max': asg['MaxSize'],
                    'desired': asg['DesiredCapacity'],
                })
        except ClientError:
            pass

    return matching


SYSTEM_NAMESPACES = {'kube-system', 'kube-public', 'kube-node-lease', 'spot-optimizer'}


def _log_action(db: Session, cluster: Cluster, schedule: HibernationSchedule,
                action_type: str, status: str, details: Dict) -> None:
    """Log hibernation action to audit trail and update schedule tracking."""
    try:
        audit = AuditLog(
            actor_id="system-hibernation",
            actor_name="Hibernation Worker",
            event=action_type,
            resource=cluster.name,
            resource_type=ResourceType.HIBERNATION,
            outcome=AuditOutcome.SUCCESS if status == "completed" else AuditOutcome.FAILURE,
            diff_after=details
        )
        db.add(audit)

        schedule.last_action = action_type
        schedule.last_action_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"[WORK-HIB-01] Failed to log action: {e}")


# ---------------------------------------------------------------------------
# Strategy Implementations - Using Modular Classes
# ---------------------------------------------------------------------------

def _namespace_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Namespace Sleep using modular NamespaceSleepStrategy.

    Delegates to backend.Hibernation_strategy.namespace_sleep module.
    All configuration and logic is defined in that module.
    """
    logger.info(f"[WORK-HIB-01] Starting Namespace Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)

    # Prepare K8s clients dict for strategy
    k8s_clients = {
        'core_v1': core_v1,
        'apps_v1': apps_v1,
        'autoscaling_v1': autoscaling_v1
    }

    # Instantiate and execute strategy
    strategy = NamespaceSleepStrategy()
    result = strategy.execute_sleep(cluster, schedule, db, k8s_clients)

    # Log action
    _log_action(db, cluster, schedule, "NAMESPACE_SLEEP", "completed", result)

    logger.info(f"[WORK-HIB-01] Namespace Sleep completed for {cluster.name}")


def _namespace_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Namespace Wake using modular NamespaceSleepStrategy.

    Delegates to backend.Hibernation_strategy.namespace_sleep module.
    """
    logger.info(f"[WORK-HIB-01] Starting Namespace Wake for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)

    # Prepare K8s clients dict for strategy
    k8s_clients = {
        'core_v1': core_v1,
        'apps_v1': apps_v1,
        'autoscaling_v1': autoscaling_v1
    }

    # Instantiate and execute strategy
    strategy = NamespaceSleepStrategy()
    result = strategy.execute_wake(cluster, schedule, db, k8s_clients)

    # Log action
    _log_action(db, cluster, schedule, "NAMESPACE_WAKE", "completed", result)

    logger.info(f"[WORK-HIB-01] Namespace Wake completed for {cluster.name}")


# ---------------------------------------------------------------------------
# Strategy B: Nuclear (Hard) - Using Modular Implementation
# ---------------------------------------------------------------------------

def _nuclear_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Nuclear Sleep using modular NuclearStrategy.

    Delegates to backend.Hibernation_strategy.nuclear module.
    """
    logger.info(f"[WORK-HIB-01] Starting Nuclear Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)

    # Instantiate and execute strategy
    strategy = NuclearStrategy()
    result = strategy.execute_sleep(cluster, schedule, db, credentials)

    # Log action
    _log_action(db, cluster, schedule, "NUCLEAR_SLEEP", "completed", result)

    logger.info(f"[WORK-HIB-01] Nuclear Sleep completed for {cluster.name}")


def _nuclear_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Nuclear Wake using modular NuclearStrategy.

    Delegates to backend.Hibernation_strategy.nuclear module.
    """
    logger.info(f"[WORK-HIB-01] Starting Nuclear Wake for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)

    # Instantiate and execute strategy
    strategy = NuclearStrategy()
    result = strategy.execute_wake(cluster, schedule, db, credentials)

    # Log action
    _log_action(db, cluster, schedule, "NUCLEAR_WAKE", "completed", result)

    logger.info(f"[WORK-HIB-01] Nuclear Wake completed for {cluster.name}")


# ---------------------------------------------------------------------------
# Strategy C: Snapshot & Restore (Safe) - Using Modular Implementation
# ---------------------------------------------------------------------------

def _snapshot_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Snapshot Sleep using modular SnapshotRestoreStrategy.

    Delegates to backend.Hibernation_strategy.snapshot_restore module.
    """
    logger.info(f"[WORK-HIB-01] Starting Snapshot Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)

    # Get K8s clients (optional for snapshot strategy)
    try:
        core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)
        k8s_clients = {
            'core_v1': core_v1,
            'apps_v1': apps_v1,
            'autoscaling_v1': autoscaling_v1
        }
    except Exception as e:
        logger.warning(f"[WORK-HIB-01] K8s API not available: {e}. Continuing without K8s clients.")
        k8s_clients = None

    # Instantiate and execute strategy
    strategy = SnapshotRestoreStrategy()
    result = strategy.execute_sleep(cluster, schedule, db, credentials, k8s_clients)

    # Log action
    _log_action(db, cluster, schedule, "SNAPSHOT_SLEEP", "completed", result)

    logger.info(f"[WORK-HIB-01] Snapshot Sleep completed for {cluster.name}")


def _snapshot_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Snapshot Wake using modular SnapshotRestoreStrategy.

    Delegates to backend.Hibernation_strategy.snapshot_restore module.
    """
    logger.info(f"[WORK-HIB-01] Starting Snapshot Wake for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)

    # Instantiate and execute strategy
    strategy = SnapshotRestoreStrategy()
    result = strategy.execute_wake(cluster, schedule, db, credentials)

    # Log action
    _log_action(db, cluster, schedule, "SNAPSHOT_WAKE", "completed", result)

    logger.info(f"[WORK-HIB-01] Snapshot Wake completed for {cluster.name}")


# ---------------------------------------------------------------------------
# Strategy Dispatch
# ---------------------------------------------------------------------------

def trigger_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """Dispatch sleep action to the appropriate strategy."""
    strategy = getattr(schedule, 'strategy', None) or HibernationStrategy.NAMESPACE_SLEEP.value

    if strategy == HibernationStrategy.NUCLEAR.value:
        _nuclear_sleep(cluster, schedule, db)
    elif strategy == HibernationStrategy.SNAPSHOT_RESTORE.value:
        _snapshot_sleep(cluster, schedule, db)
    else:
        _namespace_sleep(cluster, schedule, db)


def trigger_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """Dispatch wake action to the appropriate strategy."""
    strategy = getattr(schedule, 'strategy', None) or HibernationStrategy.NAMESPACE_SLEEP.value

    if strategy == HibernationStrategy.NUCLEAR.value:
        _nuclear_wake(cluster, schedule, db)
    elif strategy == HibernationStrategy.SNAPSHOT_RESTORE.value:
        _snapshot_wake(cluster, schedule, db)
    else:
        _namespace_wake(cluster, schedule, db)


def trigger_prewarm(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """Pre-warm is a wake triggered early."""
    logger.info(f"[WORK-HIB-01] Pre-warming cluster {cluster.name}")
    trigger_wake(cluster, schedule, db)

    schedule.last_action = "PREWARM"
    schedule.last_action_at = datetime.utcnow()
    db.commit()

    logger.info(f"[WORK-HIB-01] Pre-warm completed for {cluster.name}")


# ---------------------------------------------------------------------------
# Main Scheduler Loop
# ---------------------------------------------------------------------------

@app.task(bind=True, name="workers.hibernation.check_schedules")
def hibernation_scheduler_loop(self: Task) -> Dict[str, Any]:
    """
    Main hibernation scheduler loop - runs every 1 minute

    Checks all active hibernation schedules and triggers sleep/wake actions
    based on current time and schedule matrix.
    """
    logger.info("[WORK-HIB-01] Starting hibernation schedule check")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        # Query all active hibernation schedules (BUG FIX: was .enabled == True)
        schedules = db.query(HibernationSchedule).filter(
            HibernationSchedule.is_active == "Y"
        ).all()

        results = {
            "checked": 0,
            "sleep_triggered": 0,
            "wake_triggered": 0,
            "prewarm_triggered": 0,
            "errors": 0
        }

        for schedule in schedules:
            try:
                results["checked"] += 1
                action = process_schedule(schedule, db, redis_client)

                if action == "SLEEP":
                    results["sleep_triggered"] += 1
                elif action == "WAKE":
                    results["wake_triggered"] += 1
                elif action == "PREWARM":
                    results["prewarm_triggered"] += 1

            except Exception as e:
                logger.error(f"[WORK-HIB-01] Error processing schedule {schedule.id}: {str(e)}")
                results["errors"] += 1

        logger.info(f"[WORK-HIB-01] Schedule check complete: {results}")
        return results

    except Exception as e:
        logger.error(f"[WORK-HIB-01] Fatal error in hibernation scheduler: {str(e)}")
        raise
    finally:
        db.close()


def process_schedule(
    schedule: HibernationSchedule,
    db: Session,
    redis_client
) -> Optional[str]:
    """Process a single hibernation schedule."""
    cluster = db.query(Cluster).filter(Cluster.id == schedule.cluster_id).first()
    if not cluster:
        logger.warning(f"[WORK-HIB-01] Cluster {schedule.cluster_id} not found")
        return None

    # Convert current time to schedule's timezone
    tz = pytz.timezone(schedule.timezone)
    current_time = datetime.now(pytz.UTC).astimezone(tz)

    current_day = current_time.weekday()
    current_hour = current_time.hour

    matrix_index = (current_day * 24) + current_hour

    if len(schedule.schedule_matrix) != 168:
        logger.error(f"[WORK-HIB-01] Invalid schedule matrix for {schedule.id}")
        return None

    current_state = schedule.schedule_matrix[matrix_index]
    should_be_awake = (current_state == '1')

    # Pre-warm window: use schedule's pre_warm_minutes (BUG FIX: was hardcoded 30)
    prewarm_minutes = schedule.pre_warm_minutes or 30
    prewarm_index = (matrix_index + 1) % 168
    next_hour_state = schedule.schedule_matrix[prewarm_index]
    next_hour_awake = (next_hour_state == '1')

    current_minute = current_time.minute
    is_prewarm_window = (current_minute >= (60 - prewarm_minutes) and not should_be_awake and next_hour_awake)

    # Get cluster's current state from Redis cache
    cluster_state_key = f"cluster_state:{cluster.id}"
    cached_state = redis_client.get(cluster_state_key)

    # Determine action needed
    if is_prewarm_window and cached_state != b"PREWARM":
        logger.info(f"[WORK-HIB-01] Pre-warming cluster {cluster.name} ({prewarm_minutes} min before wake)")
        trigger_prewarm(cluster, schedule, db)
        redis_client.setex(cluster_state_key, 3600, "PREWARM")
        return "PREWARM"

    elif should_be_awake and cached_state != b"AWAKE":
        logger.info(f"[WORK-HIB-01] Waking cluster {cluster.name}")
        trigger_wake(cluster, schedule, db)
        redis_client.setex(cluster_state_key, 3600, "AWAKE")
        return "WAKE"

    elif not should_be_awake and cached_state != b"SLEEPING":
        logger.info(f"[WORK-HIB-01] Sleeping cluster {cluster.name}")
        trigger_sleep(cluster, schedule, db)
        redis_client.setex(cluster_state_key, 3600, "SLEEPING")
        return "SLEEP"

    return None


# ---------------------------------------------------------------------------
# Manual Tasks
# ---------------------------------------------------------------------------

@app.task(bind=True, name="workers.hibernation.manual_sleep")
def manual_sleep_cluster(self: Task, cluster_id: str, strategy: str = None) -> Dict[str, Any]:
    """Manually trigger cluster sleep (bypasses schedule)."""
    logger.info(f"[WORK-HIB-01] Manual sleep triggered for cluster {cluster_id}")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        # Use existing schedule if available, otherwise create dummy
        existing = db.query(HibernationSchedule).filter(
            HibernationSchedule.cluster_id == cluster_id
        ).first()

        if existing:
            schedule = existing
            if strategy:
                schedule.strategy = strategy
        else:
            schedule = HibernationSchedule(
                cluster_id=cluster_id,
                schedule_matrix="0" * 168,
                timezone="UTC",
                is_active="N",  # BUG FIX: was enabled=False
                strategy=strategy or HibernationStrategy.NAMESPACE_SLEEP.value
            )

        trigger_sleep(cluster, schedule, db)

        cluster_state_key = f"cluster_state:{cluster_id}"
        redis_client.setex(cluster_state_key, 3600, "SLEEPING")

        return {"success": True, "cluster_id": cluster_id, "action": "SLEEP"}

    except Exception as e:
        logger.error(f"[WORK-HIB-01] Manual sleep failed: {str(e)}")
        return {"success": False, "cluster_id": cluster_id, "error": str(e)}
    finally:
        db.close()


@app.task(bind=True, name="workers.hibernation.manual_wake")
def manual_wake_cluster(self: Task, cluster_id: str, strategy: str = None) -> Dict[str, Any]:
    """Manually trigger cluster wake (bypasses schedule)."""
    logger.info(f"[WORK-HIB-01] Manual wake triggered for cluster {cluster_id}")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        existing = db.query(HibernationSchedule).filter(
            HibernationSchedule.cluster_id == cluster_id
        ).first()

        if existing:
            schedule = existing
            if strategy:
                schedule.strategy = strategy
        else:
            schedule = HibernationSchedule(
                cluster_id=cluster_id,
                schedule_matrix="1" * 168,
                timezone="UTC",
                is_active="N",  # BUG FIX: was enabled=False
                strategy=strategy or HibernationStrategy.NAMESPACE_SLEEP.value
            )

        trigger_wake(cluster, schedule, db)

        cluster_state_key = f"cluster_state:{cluster_id}"
        redis_client.setex(cluster_state_key, 3600, "AWAKE")

        return {"success": True, "cluster_id": cluster_id, "action": "WAKE"}

    except Exception as e:
        logger.error(f"[WORK-HIB-01] Manual wake failed: {str(e)}")
        return {"success": False, "cluster_id": cluster_id, "error": str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Enhanced Helper Functions for Production-Grade Hibernation
# ---------------------------------------------------------------------------

def _wait_for_statefulset_ready(apps_v1, namespace: str, name: str, timeout: int = 300) -> bool:
    """
    Wait for StatefulSet pods to be ready.
    Critical for database workloads that require PVC reattachment.
    """
    import time
    start_time = time.time()

    logger.info(f"[WORK-HIB-01] Waiting for StatefulSet {namespace}/{name} to be ready...")

    while time.time() - start_time < timeout:
        try:
            sts = apps_v1.read_namespaced_stateful_set(name=name, namespace=namespace)
            ready_replicas = sts.status.ready_replicas or 0
            desired_replicas = sts.spec.replicas or 0

            if ready_replicas >= desired_replicas and desired_replicas > 0:
                logger.info(f"[WORK-HIB-01] StatefulSet {namespace}/{name} is ready ({ready_replicas}/{desired_replicas})")
                return True

            logger.debug(f"[WORK-HIB-01] StatefulSet {namespace}/{name} readiness: {ready_replicas}/{desired_replicas}")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] Error checking StatefulSet {namespace}/{name}: {e}")

        time.sleep(10)

    logger.error(f"[WORK-HIB-01] Timeout waiting for StatefulSet {namespace}/{name}")
    return False


def _wait_for_deployment_ready(apps_v1, namespace: str, name: str, timeout: int = 300) -> bool:
    """Wait for Deployment to reach desired replica count"""
    import time
    start_time = time.time()

    logger.info(f"[WORK-HIB-01] Waiting for Deployment {namespace}/{name} to be ready...")

    while time.time() - start_time < timeout:
        try:
            dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            ready_replicas = dep.status.ready_replicas or 0
            desired_replicas = dep.spec.replicas or 0

            if ready_replicas >= desired_replicas and desired_replicas > 0:
                logger.info(f"[WORK-HIB-01] Deployment {namespace}/{name} is ready ({ready_replicas}/{desired_replicas})")
                return True

            logger.debug(f"[WORK-HIB-01] Deployment {namespace}/{name} readiness: {ready_replicas}/{desired_replicas}")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] Error checking Deployment {namespace}/{name}: {e}")

        time.sleep(10)

    logger.error(f"[WORK-HIB-01] Timeout waiting for Deployment {namespace}/{name}")
    return False


def _wait_for_nodes_ready(core_v1, expected_count: int, timeout: int = 600) -> bool:
    """
    Wait for nodes to become Ready.
    Used after nuclear wake to ensure nodes are available before restoring workloads.
    """
    import time
    start_time = time.time()

    logger.info(f"[WORK-HIB-01] Waiting for {expected_count} nodes to become Ready...")

    while time.time() - start_time < timeout:
        try:
            nodes = core_v1.list_node()
            ready_nodes = sum(1 for node in nodes.items if _is_node_ready(node))

            if ready_nodes >= expected_count:
                logger.info(f"[WORK-HIB-01] All {ready_nodes} nodes are Ready")
                return True

            logger.info(f"[WORK-HIB-01] Nodes readiness: {ready_nodes}/{expected_count}")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] Error checking nodes: {e}")

        time.sleep(15)

    logger.error(f"[WORK-HIB-01] Timeout waiting for nodes")
    return False


def _is_node_ready(node) -> bool:
    """Check if a node has Ready condition set to True"""
    if node.status and node.status.conditions:
        for condition in node.status.conditions:
            if condition.type == 'Ready' and condition.status == 'True':
                return True
    return False


def _cordon_all_nodes(core_v1) -> int:
    """
    Cordon all nodes to prevent new pod scheduling.
    Returns number of nodes cordoned.
    """
    nodes = core_v1.list_node()
    cordoned = 0

    for node in nodes.items:
        try:
            patch = {'spec': {'unschedulable': True}}
            core_v1.patch_node(node.metadata.name, body=patch)
            logger.info(f"[WORK-HIB-01] Cordoned node: {node.metadata.name}")
            cordoned += 1
        except Exception as e:
            logger.error(f"[WORK-HIB-01] Failed to cordon node {node.metadata.name}: {e}")

    return cordoned


def _drain_all_nodes(core_v1, grace_period: int = 30) -> int:
    """
    Drain all nodes by evicting pods (kubectl drain equivalent).
    Returns number of pods evicted.
    """
    evicted = 0
    nodes = core_v1.list_node()

    for node in nodes.items:
        try:
            pods = core_v1.list_pod_for_all_namespaces(
                field_selector=f'spec.nodeName={node.metadata.name}'
            )

            for pod in pods.items:
                # Skip DaemonSet pods (they'll be recreated anyway)
                if pod.metadata.owner_references:
                    for owner in pod.metadata.owner_references:
                        if owner.kind == 'DaemonSet':
                            continue

                # Skip system pods
                if pod.metadata.namespace in SYSTEM_NAMESPACES:
                    continue

                try:
                    core_v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        grace_period_seconds=grace_period
                    )
                    logger.info(f"[WORK-HIB-01] Evicted pod: {pod.metadata.namespace}/{pod.metadata.name}")
                    evicted += 1
                except Exception as e:
                    logger.warning(f"[WORK-HIB-01] Failed to evict pod {pod.metadata.name}: {e}")

        except Exception as e:
            logger.error(f"[WORK-HIB-01] Failed to drain node {node.metadata.name}: {e}")

    return evicted


def _uncordon_all_nodes(core_v1) -> int:
    """
    Uncordon all nodes to allow pod scheduling.
    Returns number of nodes uncordoned.
    """
    nodes = core_v1.list_node()
    uncordoned = 0

    for node in nodes.items:
        try:
            patch = {'spec': {'unschedulable': False}}
            core_v1.patch_node(node.metadata.name, body=patch)
            logger.info(f"[WORK-HIB-01] Uncordoned node: {node.metadata.name}")
            uncordoned += 1
        except Exception as e:
            logger.error(f"[WORK-HIB-01] Failed to uncordon node {node.metadata.name}: {e}")

    return uncordoned


def _tag_resources_with_hibernation_metadata(resource, resource_type: str, strategy: str):
    """
    Tag Kubernetes resources with hibernation metadata annotations.
    Helps track what was hibernated and when.
    """
    if not resource.metadata.annotations:
        resource.metadata.annotations = {}

    resource.metadata.annotations.update({
        'hibernation.io/hibernated-at': datetime.utcnow().isoformat(),
        'hibernation.io/hibernation-type': strategy,
        'hibernation.io/resource-type': resource_type
    })

    return resource
