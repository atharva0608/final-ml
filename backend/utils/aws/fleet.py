"""
Fleet API utility — Launch spot instances via EC2 Fleet API with fallback.
"""
import uuid
import hashlib
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


def launch_via_fleet_api(ec2_client, launch_template_id: str, overrides: list,
                          subnet_id: str, tags: list, action_id: str) -> Optional[str]:
    """Launch spot instance via EC2 Fleet API with fallback to run_instances."""
    client_token = str(uuid.uuid4())
    try:
        resp = ec2_client.create_fleet(
            ClientToken=client_token,
            Type='instant',
            SpotOptions={'AllocationStrategy': 'capacity-optimized-prioritized'},
            LaunchTemplateConfigs=[{
                'LaunchTemplateSpecification': {'LaunchTemplateId': launch_template_id, 'Version': '$Latest'},
                'Overrides': overrides[:5],
            }],
            TargetCapacitySpecification={'TotalTargetCapacity': 1, 'DefaultTargetCapacityType': 'spot'},
            TagSpecifications=[{'ResourceType': 'instance', 'Tags': tags + [
                {'Key': 'spot-optimizer:action-id', 'Value': action_id},
                {'Key': 'spot-optimizer:status', 'Value': 'pending'},
            ]}],
        )
        instances = resp.get('Instances', [])
        if instances:
            ids = instances[0].get('InstanceIds', [])
            if ids:
                logger.info(f"[fleet] Launched {ids[0]} via Fleet API (action={action_id})")
                return ids[0]
    except Exception as e:
        logger.warning(f"[fleet] Fleet API failed: {e} — falling back to run_instances")
    # Fallback
    if overrides:
        top = overrides[0]
        try:
            # Issue #17: Deterministic token — same action + type → same instance on retry
            _fallback_itype = top.get('InstanceType', 't3.medium')
            _fallback_token = hashlib.sha256(
                f"{action_id}:{_fallback_itype}:fallback".encode()
            ).hexdigest()
            r = ec2_client.run_instances(
                InstanceType=_fallback_itype,
                MinCount=1, MaxCount=1,
                SubnetId=subnet_id,
                ClientToken=_fallback_token,
                InstanceMarketOptions={'MarketType': 'spot'},
                TagSpecifications=[{'ResourceType': 'instance', 'Tags': tags + [
                    {'Key': 'spot-optimizer:action-id', 'Value': action_id},
                    {'Key': 'spot-optimizer:status', 'Value': 'pending'},
                ]}],
            )
            ids = [i['InstanceId'] for i in r.get('Instances', [])]
            return ids[0] if ids else None
        except Exception as e2:
            logger.error(f"[fleet] run_instances fallback also failed: {e2}")
    return None


def dry_run_launch(ec2_client, instance_type: str, az: str) -> bool:
    """Returns True if capacity is available (DryRunOperation error = success)."""
    try:
        ec2_client.run_instances(
            InstanceType=instance_type,
            MinCount=1, MaxCount=1,
            Placement={'AvailabilityZone': az},
            InstanceMarketOptions={'MarketType': 'spot'},
            DryRun=True,
        )
        return True
    except Exception as e:
        err = str(e)
        if 'DryRunOperation' in err:
            return True
        return False
