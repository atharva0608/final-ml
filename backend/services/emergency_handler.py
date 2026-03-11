"""
Emergency Handler — Handles spot instance termination events.
"""
import json
import logging
from datetime import datetime
from backend.core.redis_client import (
    get_redis_client,
    key_emergency_in_progress,
    key_cluster_floor,
    key_cluster_cooldown,
    key_blacklist_global,
)
from backend.core.config import EMERGENCY_COOLDOWN_MINUTES
from backend.models.base import get_db

logger = logging.getLogger(__name__)


def handle_termination(instance_id, cluster_id, region, instance_type, az, node_name) -> dict:
    """
    Handle a spot instance termination event.

    Steps:
    1. Acquire emergency lock (prevent concurrent emergency handling)
    2. Trigger ExecutionController for direct replacement
    3. Blacklist terminated pool for 24h
    4. Set cluster floor
    5. Set emergency cooldown
    """
    redis = get_redis_client()
    lock_key = key_emergency_in_progress(cluster_id)
    if not redis.set(lock_key, instance_id, nx=True, ex=300):
        return {'status': 'concurrent_emergency', 'cluster_id': cluster_id}
    try:
        db = next(get_db())
        pool_key = f'{instance_type}:{az}'

        # Proactively force-delete the K8s Node object.
        # The EC2 instance is being terminated by AWS; Kubernetes marks the node
        # NotReady but does NOT auto-delete the Node object for several minutes.
        # StatefulSet pods get stuck in Terminating and block rescheduling onto
        # the warm spare until the object is gone.  Queue a FORCE_DELETE_NODE
        # so the in-cluster agent clears it immediately.
        if node_name:
            try:
                from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
                from backend.models.base import generate_uuid
                _force_del = AgentAction(
                    id=generate_uuid(),
                    cluster_id=cluster_id,
                    action_type=AgentActionType.FORCE_DELETE_NODE,
                    status=AgentActionStatus.PENDING,
                    payload={"node_name": node_name, "instance_id": instance_id,
                             "reason": "spot_interruption_hardware_termination"},
                )
                db.add(_force_del)
                db.commit()
                logger.info(
                    f'[emergency_handler] Queued FORCE_DELETE_NODE for ghost node '
                    f'{node_name} (instance {instance_id})'
                )
            except Exception as _fdn_err:
                logger.warning(f'[emergency_handler] FORCE_DELETE_NODE queue failed: {_fdn_err}')

        # Direct replacement via ExecutionController (spot attempt)
        spot_ok = False
        try:
            from backend.services.execution_controller import ExecutionController
            controller = ExecutionController(cluster_id=cluster_id, region=region)
            result = controller.execute_replacement(bypass_double_gate=True, db=db)
            spot_ok = bool(result and result.get('success'))
        except Exception as e:
            logger.error(f'[emergency_handler] ExecutionController failed: {e}')

        # On-demand last resort — triggered when spot fails during the 2-minute window.
        # We cannot afford another spot retry that may hit ICE again.
        if not spot_ok:
            logger.warning(
                f'[emergency_handler] Spot replacement failed for cluster {cluster_id} — '
                f'attempting on-demand fallback ({instance_type} in {region})'
            )
            _launch_od_emergency_fallback(
                cluster_id=cluster_id,
                region=region,
                instance_type=instance_type,
                az=az,
                db=db,
                redis=redis,
            )

        # Blacklist terminated pool for 24h
        redis.setex(key_blacklist_global(pool_key), 86400, '1')
        # Set cluster floor
        redis.setex(key_cluster_floor(cluster_id), 86400, json.dumps({'instance_type': instance_type, 'az': az}))
        # Set emergency cooldown
        redis.setex(key_cluster_cooldown(cluster_id), EMERGENCY_COOLDOWN_MINUTES * 60, '1')

        return {'status': 'handled', 'instance_id': instance_id, 'cluster_id': cluster_id}
    finally:
        redis.delete(lock_key)


def _launch_od_emergency_fallback(
    cluster_id: str,
    region: str,
    instance_type: str,
    az: str,
    db,
    redis,
) -> None:
    """
    Launch an on-demand instance as a last resort during spot interruption.

    Called only when the spot replacement attempt fails (e.g. ICE across the
    region during a mass-reclamation event).  Uses the same instance type as
    the terminated spot node to preserve cluster sizing.

    The instance is tagged so auto_rebalancer can later convert it back to
    spot once capacity recovers.
    """
    try:
        import boto3
        from backend.models.cluster import Cluster
        from backend.utils.aws.asg import get_assumed_credentials

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f'[emergency_handler] OD fallback: cluster {cluster_id} not found')
            return

        creds = get_assumed_credentials(cluster, db)
        session = boto3.Session(
            aws_access_key_id=creds.get('AccessKeyId'),
            aws_secret_access_key=creds.get('SecretAccessKey'),
            aws_session_token=creds.get('SessionToken'),
        )
        ec2 = session.client('ec2', region_name=region)

        resp = ec2.run_instances(
            InstanceType=instance_type,
            MinCount=1,
            MaxCount=1,
            Placement={'AvailabilityZone': az},
            # Explicitly request on-demand — no spot market options
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [
                    {'Key': 'spot-optimizer:status', 'Value': 'od-emergency-fallback'},
                    {'Key': 'spot-optimizer:cluster-id', 'Value': cluster_id},
                    {'Key': 'spot-optimizer:revert-to-spot', 'Value': 'true'},
                ],
            }],
        )
        od_id = resp['Instances'][0]['InstanceId']
        logger.info(
            f'[emergency_handler] OD fallback launched: {od_id} '
            f'({instance_type} in {az}) for cluster {cluster_id}'
        )
        # Mark in Redis so auto_rebalancer will convert back to spot once capacity recovers
        redis.setex(
            f'emergency:od_fallback:{cluster_id}',
            86400,
            json.dumps({'instance_id': od_id, 'instance_type': instance_type, 'az': az}),
        )

    except Exception as e:
        logger.error(
            f'[emergency_handler] OD fallback FAILED for cluster {cluster_id}: {e}',
            exc_info=True,
        )
