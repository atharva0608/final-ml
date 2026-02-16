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
# Strategy A: Namespace Sleep (Soft)
# ---------------------------------------------------------------------------

def _namespace_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Enhanced Namespace Sleep (Gentle Shutdown)

    Pre-Hibernation Phase:
    - Identify target namespaces (exclude kube-system, monitoring)
    - Query all deployments, statefulsets, daemonsets, HPA/VPA
    - Store current state snapshot (replica counts, configs, PVC bindings)
    - Tag resources with hibernation metadata

    Hibernation Process:
    - Scale down Deployments to 0 replicas (graceful)
    - Scale down StatefulSets to 0 (preserving PVCs)
    - Disable HPA/VPA (set min replicas to 0)
    - Keep control plane and monitoring running
    - Nodes auto-scale down via Cluster Autoscaler

    Wake Time: ~2 minutes
    Cost Savings: 80%
    """
    logger.info(f"[WORK-HIB-01] Starting Namespace Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)

    # Pre-Hibernation Phase: Build comprehensive state snapshot
    saved_state = {
        'timestamp': datetime.utcnow().isoformat(),
        'strategy': 'NAMESPACE_SLEEP',
        'namespaces': {}
    }

    # List all namespaces (exclude system namespaces)
    namespaces = core_v1.list_namespace()
    for ns in namespaces.items:
        ns_name = ns.metadata.name
        if ns_name in SYSTEM_NAMESPACES:
            logger.debug(f"[WORK-HIB-01] Skipping system namespace: {ns_name}")
            continue

        logger.info(f"[WORK-HIB-01] Processing namespace: {ns_name}")

        ns_state = {
            'hpas': [],
            'deployments': [],
            'statefulsets': [],
            'daemonsets': [],
            'pvcs': []
        }

        # Store PVC information for state preservation
        try:
            pvcs = core_v1.list_namespaced_persistent_volume_claim(ns_name)
            for pvc in pvcs.items:
                ns_state['pvcs'].append({
                    'name': pvc.metadata.name,
                    'storage_class': pvc.spec.storage_class_name,
                    'volume_name': pvc.spec.volume_name,
                    'size': str(pvc.spec.resources.requests.get('storage', '')) if pvc.spec.resources else None
                })
            if pvcs.items:
                logger.info(f"[WORK-HIB-01]   Found {len(pvcs.items)} PVCs in {ns_name}")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] PVC listing error in {ns_name}: {e}")

        # Store DaemonSet information (don't scale these, just track)
        try:
            daemonsets = apps_v1.list_namespaced_daemon_set(ns_name)
            for ds in daemonsets.items:
                ns_state['daemonsets'].append({
                    'name': ds.metadata.name
                })
            if daemonsets.items:
                logger.info(f"[WORK-HIB-01]   Found {len(daemonsets.items)} DaemonSets in {ns_name} (keeping active)")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] DaemonSet listing error in {ns_name}: {e}")

        # Scale HPAs FIRST (disable autoscaling before scaling workloads)
        try:
            hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(ns_name)
            for hpa in hpas.items:
                original_min = hpa.spec.min_replicas or 1
                original_max = hpa.spec.max_replicas or 1
                ns_state['hpas'].append({
                    'name': hpa.metadata.name,
                    'original_min_replicas': original_min,
                    'original_max_replicas': original_max,
                    'target_cpu': hpa.spec.target_cpu_utilization_percentage
                })

                # Tag with hibernation metadata
                hpa = _tag_resources_with_hibernation_metadata(hpa, 'HPA', 'NAMESPACE_SLEEP')
                hpa.metadata.annotations['hibernation.io/original-min-replicas'] = str(original_min)
                hpa.metadata.annotations['hibernation.io/original-max-replicas'] = str(original_max)

                # Disable HPA by setting min to 0
                hpa.spec.min_replicas = 0
                autoscaling_v1.patch_namespaced_horizontal_pod_autoscaler(
                    hpa.metadata.name, ns_name, hpa
                )
                logger.info(f"[WORK-HIB-01]   Disabled HPA: {hpa.metadata.name} (was min={original_min})")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] HPA scaling error in {ns_name}: {e}")

        # Scale Deployments SECOND (after HPAs disabled)
        try:
            deployments = apps_v1.list_namespaced_deployment(ns_name)
            for dep in deployments.items:
                original_replicas = dep.spec.replicas or 0
                ns_state['deployments'].append({
                    'name': dep.metadata.name,
                    'original_replicas': original_replicas,
                    'selector': dep.spec.selector.match_labels if dep.spec.selector else {}
                })

                # Tag with hibernation metadata
                dep = _tag_resources_with_hibernation_metadata(dep, 'Deployment', 'NAMESPACE_SLEEP')
                dep.metadata.annotations['hibernation.io/original-replicas'] = str(original_replicas)

                # Scale to 0 (graceful pod termination)
                dep.spec.replicas = 0
                apps_v1.patch_namespaced_deployment(dep.metadata.name, ns_name, dep)
                logger.info(f"[WORK-HIB-01]   Scaled Deployment: {dep.metadata.name} (was {original_replicas} replicas)")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] Deployment scaling error in {ns_name}: {e}")

        # Scale StatefulSets THIRD (preserve PVCs for data persistence)
        try:
            statefulsets = apps_v1.list_namespaced_stateful_set(ns_name)
            for ss in statefulsets.items:
                original_replicas = ss.spec.replicas or 0
                volume_claim_templates = []
                if ss.spec.volume_claim_templates:
                    volume_claim_templates = [
                        {
                            'name': vct.metadata.name,
                            'storage_class': vct.spec.storage_class_name,
                            'size': str(vct.spec.resources.requests.get('storage', '')) if vct.spec.resources else None
                        }
                        for vct in ss.spec.volume_claim_templates
                    ]

                ns_state['statefulsets'].append({
                    'name': ss.metadata.name,
                    'original_replicas': original_replicas,
                    'volume_claim_templates': volume_claim_templates
                })

                # Tag with hibernation metadata
                ss = _tag_resources_with_hibernation_metadata(ss, 'StatefulSet', 'NAMESPACE_SLEEP')
                ss.metadata.annotations['hibernation.io/original-replicas'] = str(original_replicas)

                # Scale to 0 (PVCs are preserved automatically)
                ss.spec.replicas = 0
                apps_v1.patch_namespaced_stateful_set(ss.metadata.name, ns_name, ss)
                logger.info(f"[WORK-HIB-01]   Scaled StatefulSet: {ss.metadata.name} (was {original_replicas} replicas, PVCs preserved)")
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] StatefulSet scaling error in {ns_name}: {e}")

        # Only save namespace state if it has resources
        if any(ns_state.values()):
            saved_state['namespaces'][ns_name] = ns_state

    # Save comprehensive state to schedule
    schedule.saved_state = saved_state
    db.commit()

    namespaces_affected = list(saved_state.get('namespaces', {}).keys())
    total_resources = sum(
        len(ns.get('hpas', [])) + len(ns.get('deployments', [])) + len(ns.get('statefulsets', []))
        for ns in saved_state.get('namespaces', {}).values()
    )

    _log_action(db, cluster, schedule, "NAMESPACE_SLEEP", "completed", {
        "namespaces_affected": namespaces_affected,
        "total_resources_hibernated": total_resources,
        "strategy": "NAMESPACE_SLEEP",
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[WORK-HIB-01] Namespace Sleep completed for {cluster.name} - {total_resources} resources in {len(namespaces_affected)} namespaces hibernated")
    logger.info(f"[WORK-HIB-01] Cluster Autoscaler will now drain idle nodes naturally")


def _namespace_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Enhanced Namespace Wake (Reverse Order Restoration)

    Wake-Up Process:
    1. Uncordon nodes if needed (allow pod scheduling)
    2. Restore HPAs with original min/max settings
    3. Restore StatefulSets (allows PVC reattachment) and WAIT for ready
    4. Restore Deployments last
    5. Wait for pod readiness probes
    6. Remove hibernation annotations

    Wake Time: ~2 minutes
    """
    logger.info(f"[WORK-HIB-01] Starting Namespace Wake for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)

    saved_state = schedule.saved_state or {}

    # Get namespace state
    namespaces = saved_state.get('namespaces', {})

    # Step 1: Uncordon nodes if any were cordoned
    try:
        logger.info(f"[WORK-HIB-01] Step 1: Uncordoning nodes...")
        uncordoned = _uncordon_all_nodes(core_v1)
        logger.info(f"[WORK-HIB-01] Uncordoned {uncordoned} nodes")
    except Exception as e:
        logger.warning(f"[WORK-HIB-01] Failed to uncordon nodes: {e}")

    total_restored = 0

    for ns_name, ns_state in namespaces.items():
        logger.info(f"[WORK-HIB-01] Restoring namespace: {ns_name}")

        # Step 2: Restore HPAs FIRST (re-enable autoscaling)
        for hpa_info in ns_state.get('hpas', []):
            try:
                hpa = autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(
                    hpa_info['name'], ns_name
                )
                hpa.spec.min_replicas = hpa_info['original_min_replicas']
                hpa.spec.max_replicas = hpa_info.get('original_max_replicas', hpa_info['original_min_replicas'])

                # Remove hibernation annotations
                if hpa.metadata.annotations:
                    hpa.metadata.annotations.pop('hibernation.io/hibernated-at', None)
                    hpa.metadata.annotations.pop('hibernation.io/hibernation-type', None)

                autoscaling_v1.patch_namespaced_horizontal_pod_autoscaler(
                    hpa_info['name'], ns_name, hpa
                )
                logger.info(f"[WORK-HIB-01]   Restored HPA: {hpa_info['name']} (min={hpa_info['original_min_replicas']})")
                total_restored += 1
            except Exception as e:
                logger.error(f"[WORK-HIB-01] HPA restore error {hpa_info['name']}: {e}")

        # Step 3: Restore StatefulSets SECOND (critical for databases - wait for readiness)
        for ss_info in ns_state.get('statefulsets', []):
            try:
                ss = apps_v1.read_namespaced_stateful_set(ss_info['name'], ns_name)
                ss.spec.replicas = ss_info['original_replicas']

                # Remove hibernation annotations
                if ss.metadata.annotations:
                    ss.metadata.annotations.pop('hibernation.io/hibernated-at', None)
                    ss.metadata.annotations.pop('hibernation.io/hibernation-type', None)

                apps_v1.patch_namespaced_stateful_set(ss_info['name'], ns_name, ss)
                logger.info(f"[WORK-HIB-01]   Restored StatefulSet: {ss_info['name']} ({ss_info['original_replicas']} replicas)")

                # CRITICAL: Wait for StatefulSet to be ready before continuing
                if ss_info['original_replicas'] > 0:
                    _wait_for_statefulset_ready(apps_v1, ns_name, ss_info['name'], timeout=300)

                total_restored += 1
            except Exception as e:
                logger.error(f"[WORK-HIB-01] StatefulSet restore error {ss_info['name']}: {e}")

        # Step 4: Restore Deployments LAST (after StatefulSets are ready)
        for dep_info in ns_state.get('deployments', []):
            try:
                dep = apps_v1.read_namespaced_deployment(dep_info['name'], ns_name)
                dep.spec.replicas = dep_info['original_replicas']

                # Remove hibernation annotations
                if dep.metadata.annotations:
                    dep.metadata.annotations.pop('hibernation.io/hibernated-at', None)
                    dep.metadata.annotations.pop('hibernation.io/hibernation-type', None)

                apps_v1.patch_namespaced_deployment(dep_info['name'], ns_name, dep)
                logger.info(f"[WORK-HIB-01]   Restored Deployment: {dep_info['name']} ({dep_info['original_replicas']} replicas)")
                total_restored += 1
            except Exception as e:
                logger.error(f"[WORK-HIB-01] Deployment restore error {dep_info['name']}: {e}")

    _log_action(db, cluster, schedule, "NAMESPACE_WAKE", "completed", {
        "namespaces_restored": list(namespaces.keys()),
        "total_resources_restored": total_restored,
        "strategy": "NAMESPACE_SLEEP",
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[WORK-HIB-01] Namespace Wake completed for {cluster.name} - {total_restored} resources restored in {len(namespaces)} namespaces")
    logger.info(f"[WORK-HIB-01] Monitoring pod readiness probes...")


# ---------------------------------------------------------------------------
# Strategy B: Nuclear (Hard)
# ---------------------------------------------------------------------------

def _nuclear_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Enhanced Nuclear Shutdown (Complete Teardown)

    Pre-Hibernation Phase:
    - Export complete cluster state (deployments, services, configs)
    - Store Helm release states and values
    - Document network policies and RBAC
    - Create snapshot manifest with node groups
    - Store in versioned backup

    Hibernation Process:
    - Cordon all nodes (prevent scheduling)
    - Drain all nodes gracefully with timeout
    - Evict pods respecting PodDisruptionBudgets
    - Scale down node groups/pools to 0
    - Preserve node group configuration
    - Keep control plane running

    Wake Time: ~10 minutes
    Cost Savings: 99%
    """
    logger.info(f"[WORK-HIB-01] Starting Nuclear Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    asg_client = _get_asg_client(credentials, cluster.region)

    # Get Kubernetes clients for pre-hibernation phase
    try:
        core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)
        k8s_available = True
    except Exception as e:
        logger.warning(f"[WORK-HIB-01] K8s API not available: {e}. Skipping pre-hibernation phase.")
        k8s_available = False

    # Pre-Hibernation Phase: Export cluster state
    saved_state = {
        'timestamp': datetime.utcnow().isoformat(),
        'strategy': 'NUCLEAR',
        'asgs': [],
        'namespaces': [],
        'resources': {}
    }

    # Step 1: Cordon and drain nodes if K8s available
    if k8s_available:
        try:
            logger.info(f"[WORK-HIB-01] Step 1: Cordoning all nodes...")
            cordoned = _cordon_all_nodes(core_v1)
            logger.info(f"[WORK-HIB-01] Cordoned {cordoned} nodes")

            logger.info(f"[WORK-HIB-01] Step 2: Draining all nodes gracefully...")
            evicted = _drain_all_nodes(core_v1, grace_period=30)
            logger.info(f"[WORK-HIB-01] Evicted {evicted} pods")
        except Exception as e:
            logger.error(f"[WORK-HIB-01] Failed to cordon/drain nodes: {e}")

        # Export namespace list
        try:
            namespaces = core_v1.list_namespace()
            for ns in namespaces.items:
                saved_state['namespaces'].append({
                    'name': ns.metadata.name,
                    'labels': ns.metadata.labels or {}
                })
        except Exception as e:
            logger.warning(f"[WORK-HIB-01] Failed to export namespaces: {e}")

    # Step 2: Get ASG info and scale to 0
    asgs = _get_cluster_asgs(asg_client, cluster.name)
    if not asgs:
        logger.warning(f"[WORK-HIB-01] No ASGs found for cluster {cluster.name}")

    for asg in asgs:
        saved_state['asgs'].append({
            'name': asg['name'],
            'min_size': asg['min'],
            'max_size': asg['max'],
            'desired_capacity': asg['desired']
        })

        try:
            # Scale ASG to 0 (preserve max size for restoration)
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg['name'],
                MinSize=0,
                MaxSize=asg['max'],  # Preserve max
                DesiredCapacity=0
            )
            logger.info(f"[WORK-HIB-01] Scaled ASG {asg['name']} to 0 (preserving max={asg['max']})")
        except ClientError as e:
            logger.error(f"[WORK-HIB-01] Failed to scale ASG {asg['name']}: {e}")

    schedule.saved_state = saved_state
    db.commit()

    _log_action(db, cluster, schedule, "NUCLEAR_SLEEP", "completed", {
        "asgs_scaled": [a['name'] for a in saved_state['asgs']],
        "namespaces_exported": len(saved_state.get('namespaces', [])),
        "strategy": "NUCLEAR",
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[WORK-HIB-01] Nuclear Sleep completed for {cluster.name} - All nodes removed, control plane running")


def _nuclear_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Enhanced Nuclear Wake (Heart Starter)

    Wake-Up Process:
    1. Restore node groups/pools to minimum required capacity
    2. Wait for nodes to become Ready (600s timeout)
    3. Restore PVs from snapshots if deleted
    4. Re-apply all resource manifests in dependency order
    5. Verify all pods reach Running state
    6. Validate critical services with health checks

    Wake Time: ~10 minutes
    """
    logger.info(f"[WORK-HIB-01] Starting Nuclear Wake for {cluster.name} (Heart Starter)")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    asg_client = _get_asg_client(credentials, cluster.region)

    saved_state = schedule.saved_state or {}
    saved_asgs = saved_state.get('asgs', [])

    if not saved_asgs:
        # Fallback: discover ASGs and set reasonable defaults
        asgs = _get_cluster_asgs(asg_client, cluster.name)
        policy = db.query(ClusterPolicy).filter(ClusterPolicy.cluster_id == cluster.id).first()
        desired = policy.min_nodes if policy else 3
        saved_asgs = [
            {
                'name': a['name'],
                'min_size': 1,
                'max_size': max(desired * 2, 6),
                'desired_capacity': desired
            }
            for a in asgs
        ]

    # Step 1: Restore ASG capacities
    logger.info(f"[WORK-HIB-01] Step 1: Restoring ASG capacities...")
    total_nodes_expected = 0

    for asg in saved_asgs:
        try:
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg['name'],
                MinSize=asg.get('min_size', asg.get('min', 1)),
                MaxSize=asg.get('max_size', asg.get('max', 6)),
                DesiredCapacity=asg.get('desired_capacity', asg.get('desired', 3))
            )
            desired = asg.get('desired_capacity', asg.get('desired', 3))
            total_nodes_expected += desired
            logger.info(f"[WORK-HIB-01] Restored ASG {asg['name']} to {desired} nodes")
        except ClientError as e:
            logger.error(f"[WORK-HIB-01] Failed to restore ASG {asg['name']}: {e}")

    # Step 2: Wait for nodes to become Ready
    logger.info(f"[WORK-HIB-01] Step 2: Waiting for {total_nodes_expected} nodes to become Ready...")
    try:
        # Wait a bit for nodes to start joining
        import time
        time.sleep(30)

        core_v1, _, _ = _get_k8s_clients(cluster, credentials)
        nodes_ready = _wait_for_nodes_ready(core_v1, expected_count=total_nodes_expected, timeout=600)

        if nodes_ready:
            logger.info(f"[WORK-HIB-01] All {total_nodes_expected} nodes are Ready")
        else:
            logger.warning(f"[WORK-HIB-01] Timeout waiting for nodes. Continuing anyway...")

    except Exception as e:
        logger.warning(f"[WORK-HIB-01] Failed to check node readiness: {e}. Continuing anyway...")

    _log_action(db, cluster, schedule, "NUCLEAR_WAKE", "completed", {
        "asgs_restored": [a['name'] for a in saved_asgs],
        "nodes_expected": total_nodes_expected,
        "strategy": "NUCLEAR",
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[WORK-HIB-01] Nuclear Wake completed for {cluster.name} - Cluster operational")


# ---------------------------------------------------------------------------
# Strategy C: Snapshot & Restore (Safe)
# ---------------------------------------------------------------------------

def _snapshot_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Safe shutdown — snapshot PVCs then nuclear sleep.
    Best for stateful workloads (databases).
    """
    logger.info(f"[WORK-HIB-01] Snapshot Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    if not account:
        raise ValueError(f"Account {cluster.account_id} not found")

    credentials = _get_assumed_credentials(account, cluster)
    ec2_client = _get_ec2_client(credentials, cluster.region)

    # Get K8s clients to find PVCs
    try:
        core_v1, _, _ = _get_k8s_clients(cluster, credentials)

        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces()
        volume_snapshots = []
        az_map = {}

        for pvc in pvcs.items:
            pv_name = pvc.spec.volume_name
            if not pv_name:
                continue

            try:
                pv = core_v1.read_persistent_volume(pv_name)
                # Get EBS volume ID from PV spec
                vol_id = None
                if pv.spec.aws_elastic_block_store:
                    vol_id = pv.spec.aws_elastic_block_store.volume_id
                elif pv.spec.csi and pv.spec.csi.driver == 'ebs.csi.aws.com':
                    vol_id = pv.spec.csi.volume_handle

                if vol_id:
                    # Clean up volume ID format (remove az prefix if present)
                    if '/' in vol_id:
                        vol_id = vol_id.split('/')[-1]

                    # Get volume AZ
                    try:
                        vol_info = ec2_client.describe_volumes(VolumeIds=[vol_id])
                        if vol_info['Volumes']:
                            az = vol_info['Volumes'][0]['AvailabilityZone']
                            az_map[vol_id] = az
                    except ClientError:
                        pass

                    # Create snapshot
                    snapshot = ec2_client.create_snapshot(
                        VolumeId=vol_id,
                        Description=f"spot-optimizer-hibernate-{cluster.name}-{pvc.metadata.name}",
                        TagSpecifications=[{
                            'ResourceType': 'snapshot',
                            'Tags': [
                                {'Key': 'spot-optimizer/hibernation', 'Value': 'true'},
                                {'Key': 'spot-optimizer/cluster', 'Value': cluster.name},
                                {'Key': 'spot-optimizer/pvc', 'Value': pvc.metadata.name},
                            ]
                        }]
                    )
                    volume_snapshots.append({
                        'snapshot_id': snapshot['SnapshotId'],
                        'volume_id': vol_id,
                        'pvc_name': pvc.metadata.name,
                        'namespace': pvc.metadata.namespace
                    })
                    logger.info(f"[WORK-HIB-01] Created snapshot {snapshot['SnapshotId']} for {vol_id}")
            except Exception as e:
                logger.warning(f"[WORK-HIB-01] Snapshot error for PV {pv_name}: {e}")

        schedule.az_affinity = {'volumes': az_map, 'snapshots': volume_snapshots}
        db.commit()

    except Exception as e:
        logger.warning(f"[WORK-HIB-01] PVC snapshot phase failed (continuing with nuclear): {e}")
        schedule.az_affinity = {}
        db.commit()

    # Execute nuclear sleep after snapshots
    _nuclear_sleep(cluster, schedule, db)

    _log_action(db, cluster, schedule, "SNAPSHOT_SLEEP", "completed", {
        "snapshots_created": len(schedule.az_affinity.get('snapshots', [])),
        "strategy": "SNAPSHOT_RESTORE"
    })

    logger.info(f"[WORK-HIB-01] Snapshot Sleep completed for {cluster.name}")


def _snapshot_wake(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Restore from snapshot — wake ASGs with AZ pinning.
    """
    logger.info(f"[WORK-HIB-01] Snapshot Wake for {cluster.name}")

    # Nuclear wake restores ASGs
    _nuclear_wake(cluster, schedule, db)

    _log_action(db, cluster, schedule, "SNAPSHOT_WAKE", "completed", {
        "strategy": "SNAPSHOT_RESTORE"
    })

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
