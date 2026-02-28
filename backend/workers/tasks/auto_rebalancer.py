"""Auto-Rebalancing Worker - System B: Automatic Node Migration

Executes auto-rebalancing actions created by termination_monitor.py:
1. Emergency Rebalancing (90 seconds): Triggered on termination notice
2. Graceful Rebalancing (10 minutes): Proactive migration to safer pools

Process:
- Query rebalancing_actions table for 'in_progress' actions
- Drain nodes on source pool
- Provision new nodes on target pool (via Karpenter)
- Update action status to 'completed' or 'failed'
- Calculate duration

Celery Task: Runs every 15 seconds checking for active rebalancing actions
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy.orm import Session
from kubernetes import client
from kubernetes.client.rest import ApiException

from backend.core.logger import logger
from backend.models.base import get_db
from backend.models.rebalancing_action import RebalancingAction
from backend.models.cluster import Cluster
from backend.services.karpenter_service import KarpenterService


def execute_rebalancing_action(db: Session, action: RebalancingAction):
        """Execute a single rebalancing action."""
        try:
            logger.info(f"Executing rebalancing action {action.id}: {action.cluster_id} ({action.source_pool} → {action.target_pool})")

            # Get cluster
            cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {action.cluster_id} not found")

            # Get Kubernetes API client
            karpenter_service = KarpenterService(db)
            api_client = karpenter_service._get_k8s_client(cluster)

            # Parse source and target pools
            source_instance_type, source_az = action.source_pool.split(':')
            target_instance_type, target_az = action.target_pool.split(':')

            # Step 1: Cordon nodes on source pool
            nodes_cordoned = cordon_nodes_on_pool(
                api_client=api_client,
                instance_type=source_instance_type,
                az=source_az
            )

            if nodes_cordoned == 0:
                logger.warning(f"No nodes found on source pool {action.source_pool}")

            # Step 2: Update Karpenter NodePool to prefer target pool
            # (Karpenter will provision new nodes on target pool)
            karpenter_service.sync_ml_rankings_to_nodepool(
                cluster_id=action.cluster_id,
                top_pools=[{
                    'instance_type': target_instance_type,
                    'az': target_az,
                    'ml_score': 95.0  # High score for target pool
                }],
                nodepool_name='ml-optimized'
            )

            # Step 3: Drain pods from cordoned nodes
            # (Kubernetes will reschedule pods, Karpenter will provision new nodes)
            pods_migrated = drain_nodes_on_pool(
                api_client=api_client,
                instance_type=source_instance_type,
                az=source_az
            )

            # Step 4: Mark action as completed
            action.status = 'completed'
            action.completed_at = datetime.utcnow()
            action.duration_seconds = int((action.completed_at - action.started_at).total_seconds())
            action.nodes_affected = nodes_cordoned
            action.pods_migrated = pods_migrated

            db.commit()

            logger.info(f"Rebalancing action {action.id} completed successfully ({action.duration_seconds}s, {pods_migrated} pods migrated)")

        except Exception as e:
            logger.error(f"Failed to execute rebalancing action {action.id}: {e}")

            # Mark action as failed
            action.status = 'failed'
            action.completed_at = datetime.utcnow()
            action.duration_seconds = int((action.completed_at - action.started_at).total_seconds()) if action.started_at else 0
            action.error_message = str(e)

            db.commit()

def cordon_nodes_on_pool(
    api_client,
    instance_type: str,
    az: str
) -> int:
        """
        Cordons all nodes matching instance type and AZ.

        Returns:
            Number of nodes cordoned
        """
        try:
            core_api = client.CoreV1Api(api_client)

            # List all nodes
            nodes = core_api.list_node()

            cordoned_count = 0

            for node in nodes.items:
                # Check if node matches instance type
                node_instance_type = node.metadata.labels.get('node.kubernetes.io/instance-type')

                # Check if node is in the target AZ
                node_az = node.metadata.labels.get('topology.kubernetes.io/zone')

                if node_instance_type == instance_type and node_az == az:
                    # Cordon node (mark unschedulable)
                    node.spec.unschedulable = True
                    core_api.patch_node(node.metadata.name, node)

                    logger.info(f"Cordoned node {node.metadata.name} ({instance_type} in {az})")
                    cordoned_count += 1

            return cordoned_count

        except Exception as e:
            logger.error(f"Failed to cordon nodes: {e}")
            return 0

def drain_nodes_on_pool(
    api_client,
    instance_type: str,
    az: str
) -> int:
        """
        Drains pods from nodes matching instance type and AZ.

        This evicts pods gracefully, allowing them to reschedule.
        Karpenter will provision new nodes on safer pools to handle rescheduled pods.

        Returns:
            Number of pods migrated
        """
        try:
            core_api = client.CoreV1Api(api_client)

            # List all nodes
            nodes = core_api.list_node()

            pods_migrated = 0

            for node in nodes.items:
                # Check if node matches instance type and AZ
                node_instance_type = node.metadata.labels.get('node.kubernetes.io/instance-type')
                node_az = node.metadata.labels.get('topology.kubernetes.io/zone')

                if node_instance_type == instance_type and node_az == az:
                    # Get pods on this node
                    pods = core_api.list_pod_for_all_namespaces(
                        field_selector=f'spec.nodeName={node.metadata.name}'
                    )

                    # Evict each pod
                    for pod in pods.items:
                        # Skip DaemonSet pods (they can't be evicted)
                        if pod.metadata.owner_references:
                            owner_kind = pod.metadata.owner_references[0].kind
                            if owner_kind == 'DaemonSet':
                                continue

                        try:
                            # Create eviction object
                            eviction = client.V1Eviction(
                                metadata=client.V1ObjectMeta(
                                    name=pod.metadata.name,
                                    namespace=pod.metadata.namespace
                                ),
                                delete_options=client.V1DeleteOptions(
                                    grace_period_seconds=30
                                )
                            )

                            # Evict pod
                            core_api.create_namespaced_pod_eviction(
                                name=pod.metadata.name,
                                namespace=pod.metadata.namespace,
                                body=eviction
                            )

                            pods_migrated += 1
                            logger.debug(f"Evicted pod {pod.metadata.namespace}/{pod.metadata.name}")

                        except ApiException as e:
                            if e.status == 404:
                                # Pod already deleted
                                continue
                            else:
                                logger.warning(f"Failed to evict pod {pod.metadata.namespace}/{pod.metadata.name}: {e}")

            logger.info(f"Drained {pods_migrated} pods from {instance_type} nodes in {az}")

            return pods_migrated

        except Exception as e:
            logger.error(f"Failed to drain nodes: {e}")
            return 0


def trigger_graceful_rebalancing(
    cluster_id: str,
    source_pool: str,
    target_pool: str,
    reason: str = "proactive_optimization"
) -> Dict:
    """
    Triggers graceful rebalancing (10 minutes) for a cluster.

    This is called by:
    - Scheduled optimization checks
    - Manual user action via UI
    - Pool risk score increase

    Args:
        cluster_id: Cluster to rebalance
        source_pool: Current pool (e.g., 'm5.xlarge:aps1-az1')
        target_pool: Target safer/cheaper pool
        reason: Reason for rebalancing

    Returns:
        Dict with rebalancing action details
    """
    db = next(get_db())

    try:
        # Create rebalancing action record
        rebalancing_action = RebalancingAction(
            cluster_id=cluster_id,
            trigger='graceful',
            source_pool=source_pool,
            target_pool=target_pool,
            status='in_progress',
            started_at=datetime.utcnow(),
            action_metadata={
                'reason': reason,
                'initiated_by': 'system'
            }
        )

        db.add(rebalancing_action)
        db.commit()

        logger.info(f"Graceful rebalancing triggered: {cluster_id} ({source_pool} → {target_pool})")

        return {
            'status': 'success',
            'action_id': rebalancing_action.id,
            'cluster_id': cluster_id,
            'source_pool': source_pool,
            'target_pool': target_pool,
            'trigger': 'graceful',
            'started_at': rebalancing_action.started_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to trigger graceful rebalancing: {e}")
        db.rollback()
        return {
            'status': 'error',
            'error': str(e)
        }
    finally:
        db.close()


# Celery task registration
from backend.workers.app import app

@app.task(name='workers.auto_rebalancer')
def execute_rebalancing():
    """Celery task entry point for auto-rebalancing."""
    logger.info("Auto-rebalancer task started")

    db = next(get_db())

    try:
        # Step 1: Check clusters with auto-rebalancing enabled and create actions for on-demand instances
        from backend.models.instance import Instance
        from backend.models.cluster import ClusterOptimizationSettings, StatelessRuntimeRules

        # Find clusters with unified auto-rebalance enabled
        active_settings = db.query(ClusterOptimizationSettings).filter(
            ClusterOptimizationSettings.auto_rebalance_enabled == True
        ).all()
        
        cluster_ids = [s.cluster_id for s in active_settings]
        auto_rebalance_clusters = db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).all()

        for cluster in auto_rebalance_clusters:
            # Enforce stateless runtime limits (max rebalances per 24h)
            stateless_rules = db.query(StatelessRuntimeRules).filter(StatelessRuntimeRules.cluster_id == cluster.id).first()
            max_rebalances = stateless_rules.max_rebalances_per_24h if stateless_rules else 5
            
            recent_rebalances = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.trigger == 'auto_rebalance',
                RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24)
            ).count()
            
            if recent_rebalances >= max_rebalances:
                logger.info(f"Skipping auto-rebalance for cluster {cluster.name}: hit daily limit of {max_rebalances}")
                continue

            # Find on-demand instances that should be migrated to spot
            on_demand_instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == "on_demand"
            ).all()

            actions_created = 0
            for instance in on_demand_instances:
                # Check if we hit the limit during this loop
                if (recent_rebalances + actions_created) >= max_rebalances:
                    logger.info(f"Hit daily limit while creating rebalancing actions for cluster {cluster.name}")
                    break

                # Check if there's already a pending/in_progress action for this instance
                existing_action = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.source_pool.contains(instance.instance_type),
                    RebalancingAction.status.in_(['pending', 'in_progress'])
                ).first()

                if existing_action:
                    logger.debug(f"Action already exists for {instance.instance_id}")
                    continue

                # Create new rebalancing action: on-demand → spot
                source_pool = f"{instance.instance_type}:{instance.availability_zone}"
                target_pool = f"{instance.instance_type}:{instance.availability_zone}"  # Same type, different lifecycle

                rebalancing_action = RebalancingAction(
                    cluster_id=cluster.id,
                    trigger='auto_rebalance',
                    source_pool=source_pool,
                    target_pool=target_pool,
                    status='in_progress',
                    started_at=datetime.utcnow(),
                    action_metadata={
                        'reason': 'automatic_on_demand_to_spot_migration',
                        'initiated_by': 'auto_rebalancer',
                        'instance_id': instance.instance_id
                    }
                )

                db.add(rebalancing_action)
                actions_created += 1
                logger.info(f"Created auto-rebalance action for {instance.instance_id} in cluster {cluster.name}")

        db.commit()

        # Step 2: Execute pending rebalancing actions
        pending_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status == 'in_progress'
        ).all()

        if not pending_actions:
            logger.debug("No pending rebalancing actions")
            return

        logger.info(f"Found {len(pending_actions)} pending rebalancing actions")

        # Process each action
        for action in pending_actions:
            execute_rebalancing_action(db, action)

        logger.info("Auto-rebalancer task completed successfully")

    except Exception as e:
        logger.error(f"Auto-rebalancer task failed: {e}")
        raise
    finally:
        db.close()
