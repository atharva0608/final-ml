"""
ASG Helper Utilities — Auto Scaling Group Management
=====================================================
Provides helpers for suspending/resuming ASG processes, detaching instances,
and adjusting MinSize to support last-On-Demand-node replacement.

Used by auto_rebalancer.py (the brain) during rebalance cycles.
"""

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def get_assumed_credentials(cluster, db) -> dict:
    """
    Build assumed-role credentials dict for cross-account AWS access.
    Returns empty dict if no role ARN is configured (uses instance profile).
    """
    import boto3

    role_arn = cluster.aws_role_arn
    external_id = cluster.aws_external_id
    region = cluster.region or "ap-south-1"

    if not role_arn and cluster.account_id:
        try:
            from backend.models.account import Account
            acct = db.query(Account).filter(Account.id == cluster.account_id).first()
            if acct:
                role_arn = acct.role_arn
                external_id = acct.external_id
        except Exception:
            pass

    if not role_arn:
        return {}

    # Load platform credentials for STS
    from backend.models.system_config import SystemConfig
    pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
    ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
    plat_key = pk.value if pk and pk.value else None
    plat_secret = ps.value if ps and ps.value else None

    sts_kwargs = {"region_name": region}
    if plat_key and plat_secret:
        sts_kwargs["aws_access_key_id"] = plat_key
        sts_kwargs["aws_secret_access_key"] = plat_secret

    sts = boto3.client("sts", **sts_kwargs)
    assume_kw = {
        "RoleArn": role_arn,
        "RoleSessionName": "spot-rebalancer-asg-ops",
    }
    if external_id:
        assume_kw["ExternalId"] = external_id

    assumed = sts.assume_role(**assume_kw)
    creds = assumed["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def _get_asg_client(region: str, credentials: dict):
    """Create an autoscaling boto3 client with optional assumed credentials."""
    import boto3
    return boto3.client("autoscaling", region_name=region, **credentials)


def get_asg_for_instance(instance_id: str, region: str, credentials: dict) -> Optional[str]:
    """
    Resolve the Auto Scaling Group name for a given EC2 instance.
    Returns None if the instance is not part of any ASG.
    """
    try:
        client = _get_asg_client(region, credentials)
        resp = client.describe_auto_scaling_instances(InstanceIds=[instance_id])
        instances = resp.get("AutoScalingInstances", [])
        if instances:
            return instances[0]["AutoScalingGroupName"]
        return None
    except Exception as e:
        logger.warning(f"[asg] Failed to resolve ASG for {instance_id}: {e}")
        return None


def describe_auto_scaling_group(asg_name: str, region: str, credentials: dict) -> Optional[Dict]:
    """
    Describe an Auto Scaling Group. Returns the ASG dict or None.
    Keys: MinSize, MaxSize, DesiredCapacity, Instances, etc.
    """
    try:
        client = _get_asg_client(region, credentials)
        resp = client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = resp.get("AutoScalingGroups", [])
        return groups[0] if groups else None
    except Exception as e:
        logger.error(f"[asg] Failed to describe ASG '{asg_name}': {e}")
        return None


# Processes to suspend during rebalance to prevent ASG interference
_SUSPEND_PROCESSES = ["ReplaceUnhealthy", "AZRebalance", "Launch"]


def suspend_asg_processes(asg_name: str, region: str, credentials: dict) -> bool:
    """
    Suspend ASG processes (ReplaceUnhealthy, AZRebalance, Launch) to prevent
    the ASG from reacting during node swap. Returns True on success.
    """
    try:
        client = _get_asg_client(region, credentials)
        client.suspend_processes(
            AutoScalingGroupName=asg_name,
            ScalingProcesses=_SUSPEND_PROCESSES,
        )
        logger.info(f"[asg] Suspended processes {_SUSPEND_PROCESSES} on ASG '{asg_name}'")
        return True
    except Exception as e:
        logger.error(f"[asg] Failed to suspend processes on ASG '{asg_name}': {e}")
        return False


def resume_asg_processes(asg_name: str, region: str, credentials: dict) -> bool:
    """
    Resume previously suspended ASG processes. Returns True on success.
    """
    try:
        client = _get_asg_client(region, credentials)
        client.resume_processes(
            AutoScalingGroupName=asg_name,
            ScalingProcesses=_SUSPEND_PROCESSES,
        )
        logger.info(f"[asg] Resumed processes {_SUSPEND_PROCESSES} on ASG '{asg_name}'")
        return True
    except Exception as e:
        logger.error(f"[asg] Failed to resume processes on ASG '{asg_name}': {e}")
        return False


def update_asg_min_size(asg_name: str, new_min: int, region: str, credentials: dict) -> bool:
    """
    Temporarily update ASG MinSize. Used when the last OD node needs
    to be detached and MinSize > new desired capacity.
    Returns True on success.
    """
    try:
        client = _get_asg_client(region, credentials)
        client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=new_min,
        )
        logger.info(f"[asg] Updated ASG '{asg_name}' MinSize → {new_min}")
        return True
    except Exception as e:
        logger.error(f"[asg] Failed to update MinSize on ASG '{asg_name}': {e}")
        return False


def detach_instance_from_asg(
    instance_id: str,
    asg_name: str,
    region: str,
    credentials: dict,
    decrement_desired: bool = True,
) -> bool:
    """
    Detach an EC2 instance from its ASG.
    With decrement_desired=True, the ASG's desired capacity is permanently reduced.
    Returns True on success.
    """
    try:
        client = _get_asg_client(region, credentials)
        client.detach_instances(
            InstanceIds=[instance_id],
            AutoScalingGroupName=asg_name,
            ShouldDecrementDesiredCapacity=decrement_desired,
        )
        logger.info(
            f"[asg] Detached {instance_id} from ASG '{asg_name}' "
            f"(decrement_desired={decrement_desired})"
        )
        return True
    except Exception as e:
        logger.error(f"[asg] Failed to detach {instance_id} from ASG '{asg_name}': {e}")
        return False


def lower_min_size(asg_client, asg_name: str) -> int:
    """
    Decrement ASG MinSize by 1. Returns original min size.
    Idempotent — safe to call even if already at 0.
    """
    try:
        resp = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = resp.get("AutoScalingGroups", [])
        if not groups:
            logger.warning(f"[asg] lower_min_size: ASG '{asg_name}' not found")
            return 0
        original_min = groups[0]["MinSize"]
        new_min = max(0, original_min - 1)
        asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=new_min,
        )
        logger.info(f"[asg] Lowered ASG '{asg_name}' MinSize {original_min} → {new_min}")
        return original_min
    except Exception as e:
        logger.error(f"[asg] lower_min_size failed for '{asg_name}': {e}")
        return 0


def restore_min_size(asg_client, asg_name: str, original_min: int):
    """
    Restore ASG MinSize to original_min. Idempotent.
    """
    try:
        asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=original_min,
        )
        logger.info(f"[asg] Restored ASG '{asg_name}' MinSize → {original_min}")
    except Exception as e:
        logger.error(f"[asg] restore_min_size failed for '{asg_name}': {e}")


def handle_last_od_node_asg(
    instance_id: str,
    region: str,
    credentials: dict,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Full ASG handling sequence for the last On-Demand node swap.

    Returns (success, asg_name, original_min_size).
    Call resume_asg_processes() after termination to clean up.

    Steps:
    1. Resolve ASG → suspend processes
    2. Record original MinSize and DesiredCapacity
    3. If MinSize > new_desired, lower MinSize
    4. Detach instance with ShouldDecrementDesiredCapacity=True
    """
    asg_name = get_asg_for_instance(instance_id, region, credentials)
    if not asg_name:
        logger.info(f"[asg] Instance {instance_id} not in any ASG — no ASG handling needed")
        return (True, None, None)

    # Step 1: Suspend ASG processes
    if not suspend_asg_processes(asg_name, region, credentials):
        return (False, asg_name, None)

    # Step 2: Read current config
    asg_info = describe_auto_scaling_group(asg_name, region, credentials)
    if not asg_info:
        resume_asg_processes(asg_name, region, credentials)
        return (False, asg_name, None)

    original_min = asg_info["MinSize"]
    original_desired = asg_info["DesiredCapacity"]
    new_desired = original_desired - 1

    # Step 3: Lower MinSize if it would block detach
    if original_min > new_desired:
        if not update_asg_min_size(asg_name, max(0, new_desired), region, credentials):
            resume_asg_processes(asg_name, region, credentials)
            return (False, asg_name, original_min)
        logger.info(
            f"[asg] Lowered ASG '{asg_name}' MinSize {original_min} → {new_desired} "
            f"to allow last-OD detach"
        )

    # Step 4: Detach instance
    if not detach_instance_from_asg(instance_id, asg_name, region, credentials, decrement_desired=True):
        # Restore MinSize on failure
        if original_min > new_desired:
            update_asg_min_size(asg_name, original_min, region, credentials)
        resume_asg_processes(asg_name, region, credentials)
        return (False, asg_name, original_min)

    logger.info(
        f"[asg] Last-OD handling complete: {instance_id} detached from '{asg_name}', "
        f"desired {original_desired} → {new_desired}"
    )
    return (True, asg_name, original_min)
