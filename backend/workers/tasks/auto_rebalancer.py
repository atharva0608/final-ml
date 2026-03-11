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

import boto3
from botocore.exceptions import ClientError

from backend.core.logger import logger
from backend.models.base import get_db
from backend.models.rebalancing_action import RebalancingAction
from backend.models.cluster import Cluster
from backend.models.instance import Instance, InstanceLifecycle


def _sync_instance_state_from_aws(db: Session, cluster: Cluster):
    """
    Pull real EC2 instance lifecycle from AWS and sync to the DB.
    This ensures the platform's source of truth is AWS, not assumed DB state.
    Requires cluster.aws_role_arn to be configured.
    """
    # Resolve role ARN: prefer cluster-level, fall back to linked account
    role_arn = cluster.aws_role_arn
    external_id = cluster.aws_external_id
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
        logger.debug(f"[aws_sync] Cluster {cluster.name}: no role ARN configured, skipping sync")
        return

    try:
        # Use stored platform credentials from the system_configs table
        # (same pattern as AccountService._get_platform_client — no hardcoded keys)
        from backend.models.system_config import SystemConfig

        _key_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        _sec_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        _reg_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()

        platform_key    = _key_row.value if _key_row and _key_row.value else None
        platform_secret = _sec_row.value if _sec_row and _sec_row.value else None
        platform_region = (_reg_row.value if _reg_row and _reg_row.value else None) or cluster.region or 'ap-south-1'

        if not platform_key or not platform_secret:
            logger.debug(
                f"[aws_sync] Platform AWS credentials not configured in Admin Settings; "
                f"skipping real-time sync for cluster {cluster.name}"
            )
            return

        # Step 1: Build STS client with platform credentials
        sts = boto3.client(
            'sts',
            aws_access_key_id=platform_key,
            aws_secret_access_key=platform_secret,
            region_name=platform_region,
        )

        # Step 2: Assume the client account's role via STS
        assume_kwargs = {
            'RoleArn': role_arn,
            'RoleSessionName': 'SpotOptimizerStateSync',
        }
        if external_id:
            assume_kwargs['ExternalId'] = external_id

        creds = sts.assume_role(**assume_kwargs)['Credentials']
        ec2 = boto3.client(
            'ec2',
            region_name=cluster.region or 'ap-south-1',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )

        # Describe running instances tagged for this cluster (EKS standard tag)
        response = ec2.describe_instances(
            Filters=[
                {'Name': f'tag:kubernetes.io/cluster/{cluster.name}', 'Values': ['owned', 'shared']},
                {'Name': 'instance-state-name', 'Values': ['running']},
            ]
        )

        # Build map: EC2 instance_id → (lifecycle, instance_type, az, private_ip) from AWS
        aws_instance_map = {}
        for reservation in response.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                iid = inst['InstanceId']
                # EC2 DescribeInstances: InstanceLifecycle = 'spot' | 'scheduled' | absent (on-demand)
                raw_lc = inst.get('InstanceLifecycle', 'on-demand')
                itype = inst.get('InstanceType', '')
                az = (inst.get('Placement') or {}).get('AvailabilityZone', '')
                private_ip = inst.get('PrivateIpAddress', '')
                aws_instance_map[iid] = {
                    'lifecycle': raw_lc, 'instance_type': itype, 'az': az,
                    'private_ip': private_ip,
                }
        aws_lifecycle_map = aws_instance_map  # keep name for backward compat check below

        # Build set of instance_ids already in DB for this cluster (needed for both paths below)
        db_instances = db.query(Instance).filter(Instance.cluster_id == cluster.id).all()
        db_id_map = {inst.instance_id: inst for inst in db_instances}

        if not aws_lifecycle_map:
            logger.warning(f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                           f"(check tag kubernetes.io/cluster/{cluster.name} on EC2 instances) "
                           f"— marking all DB instances as terminated")
            # Still mark all running DB instances as terminated (cluster may have been scaled to 0)
            for db_inst in db_instances:
                if db_inst.state == 'running':
                    db_inst.state = 'terminated'
            cluster.spot_count = 0
            cluster.on_demand_node_count = 0
            db.commit()
            return

        spot_count = 0
        od_count = 0
        corrected = 0
        created = 0

        for aws_iid, aws_data in aws_instance_map.items():
            aws_raw_lc   = aws_data['lifecycle']
            aws_itype    = aws_data['instance_type']
            aws_az       = aws_data['az']
            aws_priv_ip  = aws_data.get('private_ip', '')
            real_lifecycle = InstanceLifecycle.SPOT if aws_raw_lc == 'spot' else InstanceLifecycle.ON_DEMAND

            # Derive the K8s node hostname from the private IP (EKS convention)
            # e.g. 192.168.3.201 → ip-192-168-3-201.ap-south-1.compute.internal
            derived_node_name = None
            if aws_priv_ip:
                _region = cluster.region or 'ap-south-1'
                derived_node_name = f"ip-{aws_priv_ip.replace('.', '-')}.{_region}.compute.internal"

            db_inst = db_id_map.get(aws_iid)
            if db_inst is None:
                # ── NEW: create a DB record for every AWS instance we discover ──
                # Truncate instance_id to 20 chars (VARCHAR(20) constraint).
                safe_iid = aws_iid[:20]
                # Check again with the (possibly truncated) id to avoid duplicate
                if not db.query(Instance).filter(Instance.instance_id == safe_iid).first():
                    new_inst = Instance(
                        cluster_id=cluster.id,
                        instance_id=safe_iid,
                        instance_type=aws_itype or "t3.medium",
                        lifecycle=real_lifecycle,
                        az=aws_az or f"{cluster.region or 'ap-south-1'}a",
                        price=0.0,  # real price populated by pricing_collector worker
                        state='running',
                        status='READY',
                        architecture='amd64',
                        node_name=derived_node_name,  # EKS K8s node hostname
                    )
                    db.add(new_inst)
                    db.flush()  # get the id so we can use it below
                    created += 1
                    logger.info(
                        f"[aws_sync] Created instance record {safe_iid} "
                        f"(node={derived_node_name}, {aws_itype}, {real_lifecycle.value}) for cluster {cluster.name}"
                    )
                    db_inst = new_inst
            else:
                # Update existing record to match AWS truth
                changed = False
                if db_inst.lifecycle != real_lifecycle:
                    db_inst.lifecycle = real_lifecycle
                    changed = True
                if aws_itype and db_inst.instance_type != aws_itype:
                    db_inst.instance_type = aws_itype
                    changed = True
                if aws_az and db_inst.az != aws_az:
                    db_inst.az = aws_az
                    changed = True
                # Set node_name if not already stored
                if not db_inst.node_name and derived_node_name:
                    db_inst.node_name = derived_node_name
                    changed = True
                if changed:
                    logger.warning(
                        f"[aws_sync] Corrected {db_inst.instance_id}: "
                        f"lifecycle={real_lifecycle.value}, type={aws_itype}, az={aws_az}, node={derived_node_name}"
                    )
                    corrected += 1

            # Delete any ip- placeholder record that corresponds to this real instance.
            # These are created by the daemon-set metrics batch before aws_sync runs.
            if derived_node_name:
                placeholder_short = derived_node_name.split('.')[0]  # e.g. 'ip-192-168-3-201'
                dup = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.instance_id == placeholder_short,
                ).first()
                if dup:
                    # Transfer fresh utilisation data to the real instance before deleting
                    if db_inst and dup.cpu_util is not None:
                        if db_inst.cpu_util is None or dup.cpu_util > 0:
                            db_inst.cpu_util = dup.cpu_util
                            db_inst.memory_util = dup.memory_util
                    db.delete(dup)
                    logger.info(f"[aws_sync] Deleted placeholder {placeholder_short} (merged into {aws_iid[:20]})")

            if real_lifecycle == InstanceLifecycle.SPOT:
                spot_count += 1
            else:
                od_count += 1

        # Mark DB instances NOT found in AWS running set as terminated.
        # This cleans up stale records left by terminated/replaced EC2 instances.
        # SKIP placeholder records whose instance_id is a K8s hostname (e.g. ip-192-168-3-201)
        # rather than a real EC2 instance ID (always starts with "i-").
        aws_running_truncated = {aws_iid[:20] for aws_iid in aws_instance_map.keys()}
        terminated_count = 0
        for db_inst in db_instances:
            if not db_inst.instance_id or not db_inst.instance_id.startswith('i-'):
                # Placeholder record auto-created from daemon-set metrics — leave alone
                continue
            if db_inst.instance_id not in aws_running_truncated and db_inst.state == 'running':
                db_inst.state = 'terminated'
                terminated_count += 1
                logger.info(
                    f"[aws_sync] Marked {db_inst.instance_id} as terminated "
                    f"(not found in AWS running instances for cluster {cluster.name})"
                )

        # Sync cluster-level spot/od counters to match AWS reality
        cluster.spot_count = spot_count
        cluster.on_demand_node_count = od_count
        db.commit()

        logger.warning(
            f"[aws_sync] Cluster {cluster.name}: {spot_count} SPOT, {od_count} ON_DEMAND "
            f"({corrected} updated, {created} created, {terminated_count} terminated, "
            f"{len(aws_lifecycle_map)} instances found in AWS)"
        )

    except ClientError as e:
        logger.warning(f"[aws_sync] AWS API error syncing cluster {cluster.name}: {e}")
    except Exception as e:
        logger.warning(f"[aws_sync] Sync failed for cluster {cluster.name}: {e}")


def _launch_spot_instance_direct(
    db, cluster, source_instance_id: str,
    target_instance_types: list, target_az: str, region: str
):
    """
    Launch a spot EC2 instance for non-Karpenter clusters.

    Copies AMI, subnet, security groups, IAM instance profile, and cluster tags
    from the source OD instance, then calls run_instances() with spot market options.
    Tries each target_instance_type in order, falling back on InsufficientInstanceCapacity.

    Returns the new EC2 instance_id on success, or None on failure.
    """
    try:
        import boto3 as _b3f
        from botocore.exceptions import ClientError as _CE
        from backend.models.system_config import SystemConfig as _SC

        # Load stored platform credentials
        _pk = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_ACCESS_KEY").first()
        _ps = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_SECRET").first()
        _plat_key    = (_pk.value if _pk and _pk.value else None)
        _plat_secret = (_ps.value if _ps and _ps.value else None)

        # Resolve IAM role for cross-account access
        _creds = {}
        _role_arn = cluster.aws_role_arn
        _ext_id   = cluster.aws_external_id
        if not _role_arn and cluster.account_id:
            try:
                from backend.models.account import Account as _Acct
                _acct = db.query(_Acct).filter(_Acct.id == cluster.account_id).first()
                if _acct:
                    _role_arn = _acct.role_arn
                    _ext_id   = _acct.external_id
            except Exception:
                pass

        if _plat_key and _plat_secret:
            if _role_arn:
                _sts = _b3f.client("sts",
                                   aws_access_key_id=_plat_key,
                                   aws_secret_access_key=_plat_secret,
                                   region_name=region)
                _kw = {"RoleArn": _role_arn, "RoleSessionName": "spot-direct-launch"}
                if _ext_id:
                    _kw["ExternalId"] = _ext_id
                _assumed = _sts.assume_role(**_kw)
                _c = _assumed["Credentials"]
                _creds = {
                    "aws_access_key_id":     _c["AccessKeyId"],
                    "aws_secret_access_key": _c["SecretAccessKey"],
                    "aws_session_token":     _c["SessionToken"],
                }
            else:
                _creds = {"aws_access_key_id": _plat_key, "aws_secret_access_key": _plat_secret}

        _ec2 = _b3f.client("ec2", region_name=region, **_creds)

        # Describe source instance to copy launch parameters
        _resp = _ec2.describe_instances(InstanceIds=[source_instance_id])
        _src  = _resp["Reservations"][0]["Instances"][0]

        _ami_id       = _src["ImageId"]
        _subnet_id    = _src.get("SubnetId", "")
        _sg_ids       = [sg["GroupId"] for sg in _src.get("SecurityGroups", [])]
        _iam_profile  = _src.get("IamInstanceProfile", {}).get("Arn", "")
        _key_name     = _src.get("KeyName", "")

        # CRITICAL: Copy user-data from source instance.
        # EKS bootstrap script (/etc/eks/bootstrap.sh) is NOT baked into the AMI —
        # it is passed as user-data at launch time. Without it the new node's kubelet
        # never starts and the node never joins the cluster.
        _user_data_b64 = ""
        try:
            _ud_resp = _ec2.describe_instance_attribute(
                InstanceId=source_instance_id, Attribute="userData"
            )
            _user_data_b64 = _ud_resp.get("UserData", {}).get("Value", "")
        except Exception as _ud_err:
            logger.warning(
                f"[auto_rebalancer] Could not fetch user-data from {source_instance_id}: "
                f"{_ud_err} — new spot node may not join the cluster"
            )

        # Copy existing tags; add/update cluster ownership and platform marker
        _tags = [t for t in _src.get("Tags", []) if not t["Key"].startswith("aws:")]
        _cluster_tag = f"kubernetes.io/cluster/{cluster.name}"
        _tags = [t for t in _tags if t["Key"] not in (_cluster_tag, "spot-optimizer:status")]
        _tags.append({"Key": _cluster_tag, "Value": "owned"})
        _tags.append({"Key": "spot-optimizer:launched-by", "Value": "spot-optimizer-direct"})
        # scan_orphans relies on this tag to detect unjoined instances (15-min timeout)
        _tags.append({"Key": "spot-optimizer:status", "Value": "pending"})

        # If target AZ requested, find a subnet in that AZ (same VPC)
        _target_subnet = _subnet_id
        if target_az and _src.get("VpcId"):
            try:
                _sn_resp = _ec2.describe_subnets(Filters=[
                    {"Name": "vpc-id",            "Values": [_src["VpcId"]]},
                    {"Name": "availabilityZone",   "Values": [target_az]},
                    {"Name": "state",              "Values": ["available"]},
                ])
                if _sn_resp.get("Subnets"):
                    _target_subnet = _sn_resp["Subnets"][0]["SubnetId"]
            except Exception:
                pass  # Fall back to source subnet

        # Try each instance type in priority order; skip on capacity errors
        for _itype in (target_instance_types or ["t3.medium"])[:6]:
            try:
                # Use NetworkInterfaces instead of top-level SubnetId/SecurityGroupIds
                # so we can explicitly set AssociatePublicIpAddress=False.
                # EKS worker nodes must use private IPs only — they communicate via
                # VPC CNI and should never be reachable from the internet directly.
                # Using top-level SubnetId inherits the subnet's MapPublicIpOnLaunch
                # setting (True for public subnets), assigning a spurious public IP.
                _run_kwargs = {
                    "ImageId":      _ami_id,
                    "InstanceType": _itype,
                    "MinCount": 1, "MaxCount": 1,
                    "NetworkInterfaces": [{
                        "DeviceIndex": 0,
                        "SubnetId": _target_subnet,
                        "Groups": _sg_ids,
                        "AssociatePublicIpAddress": False,
                    }],
                    "InstanceMarketOptions": {
                        "MarketType": "spot",
                        "SpotOptions": {"SpotInstanceType": "one-time"},
                    },
                    "TagSpecifications": [{"ResourceType": "instance", "Tags": _tags}],
                }
                if _user_data_b64:
                    _run_kwargs["UserData"] = _user_data_b64  # base64-encoded already
                if _iam_profile:
                    _run_kwargs["IamInstanceProfile"] = {"Arn": _iam_profile}
                if _key_name:
                    _run_kwargs["KeyName"] = _key_name

                _run_resp = _ec2.run_instances(**_run_kwargs)
                _new_id   = _run_resp["Instances"][0]["InstanceId"]
                _actual_az = _run_resp["Instances"][0].get("Placement", {}).get("AvailabilityZone", target_az or "")
                logger.info(
                    f"[auto_rebalancer] Direct spot launch: {_itype} in {_actual_az} "
                    f"→ EC2 {_new_id} (cluster {cluster.name})"
                )
                return _new_id, _itype, _actual_az  # actual type + AZ used

            except _CE as _ce:
                _code = _ce.response["Error"]["Code"]
                if _code in ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow",
                             "InstanceLimitExceeded", "Unsupported"):
                    logger.warning(
                        f"[auto_rebalancer] {_itype} unavailable ({_code}), trying next type"
                    )
                    continue
                raise  # Unexpected error — propagate

        logger.error(
            f"[auto_rebalancer] All instance types exhausted for cluster {cluster.name} "
            f"— no spot capacity available in {target_az or 'any AZ'}"
        )
        return None, None, None

    except Exception as _e:
        logger.error(f"[auto_rebalancer] _launch_spot_instance_direct failed: {_e}")
        return None, None, None


def execute_rebalancing_action(db: Session, action: RebalancingAction):
        """Execute a single rebalancing action with full cross-system safety gates."""
        from backend.core.redis_client import get_redis_client, key_cluster_cooldown, key_rebalance_lock
        from backend.services.cooldown_controller import CooldownController
        from backend.services.distributed_locks import distributed_lock

        try:
            logger.info(f"Executing rebalancing action {action.id}: {action.cluster_id} ({action.source_pool} → {action.target_pool})")

            cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {action.cluster_id} not found")

            _redis = get_redis_client()

            # ── CLUSTER COOLDOWN GUARD ───────────────────────────────────────
            # Check if cluster-level cooldown is active (set by emergency or recent rebalance)
            _cooldown_key = key_cluster_cooldown(action.cluster_id)
            if _redis.exists(_cooldown_key):
                ttl = _redis.ttl(_cooldown_key)
                logger.info(
                    f"[auto_rebalancer] Cluster {action.cluster_id} cooldown active "
                    f"({ttl}s remaining) — deferring action {action.id}"
                )
                action.status = 'deferred'
                action.error_message = f"Cluster cooldown active ({ttl}s remaining)"
                db.commit()
                return

            # ── CONCURRENCY LOCK GUARD ───────────────────────────────────────
            # Ensure only one rebalancing cycle runs at a time per cluster
            _lock_key = key_rebalance_lock(action.cluster_id)
            _lock_acquired = _redis.set(_lock_key, action.id, nx=True, ex=600)
            if not _lock_acquired:
                logger.info(
                    f"[auto_rebalancer] Rebalance already in progress for cluster "
                    f"{action.cluster_id} — deferring action {action.id}"
                )
                action.status = 'deferred'
                action.error_message = "Rebalance lock held by concurrent action"
                db.commit()
                return

            _cooldown = CooldownController(_redis)

            # ── CROSS-SYSTEM SAFETY GATE 1: Stabilization lock ──────────────
            # Another system acted recently — wait for the cluster to reach steady state
            is_locked, remaining = _cooldown.is_stabilization_locked(action.cluster_id)
            if is_locked:
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: stabilization lock active "
                    f"({remaining}s remaining) — cluster not yet stable after last operation"
                )
                action.status = 'deferred'
                action.error_message = f"Stabilization lock active ({remaining}s remaining)"
                db.commit()
                return

            # ── CROSS-SYSTEM SAFETY GATE 2: Substitute mutual exclusion ─────
            # SubstituteManager is in mid-flight — do NOT drain the node it is prewarming
            sub_state_raw = _redis.get(f"spot:substitute:state:{action.cluster_id}")
            sub_state = (sub_state_raw.decode('utf-8') if isinstance(sub_state_raw, bytes) else sub_state_raw) or "IDLE"
            # READY = warm spare is standing by (good! use it). Only block PREWARMING/RELEASING.
            if sub_state in ("PREWARMING", "RELEASING"):
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: substitute is {sub_state} "
                    f"— draining would kill the substitute node mid-flight"
                )
                action.status = 'deferred'
                action.error_message = f"Substitute in state {sub_state} — deferred to avoid conflict"
                db.commit()
                return

            # ── CROSS-SYSTEM SAFETY GATE 3: Resize cooldown ─────────────────
            # Right-sizing just executed for this cluster — give it time before rebalancing
            if _redis.exists(f"spot:cooldown:action:resize:{action.cluster_id}"):
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: resize cooldown active "
                    f"— right-sizing is mid-execution for cluster {action.cluster_id}"
                )
                action.status = 'deferred'
                action.error_message = "Resize cooldown active — deferred"
                db.commit()
                return

            source_instance_type, source_az = action.source_pool.split(':') if ':' in action.source_pool else (action.source_pool, '')
            target_instance_type, target_az = action.target_pool.split(':') if ':' in action.target_pool else (action.target_pool, '')

            nodes_cordoned = 0
            pods_migrated = 0

            # ── DISTRIBUTED LOCK: one system drains this cluster at a time ───
            lock_key = f"lock:node_action:{action.cluster_id}"
            try:
                with distributed_lock(lock_key, timeout=180):
                    from backend.models.agent_action import AgentAction, AgentActionType

                    metadata = action.action_metadata or {}
                    instance_id_for_action = metadata.get('instance_id', '')

                    # Guard: if instance_id is a K8s hostname placeholder (not a real EC2 ID),
                    # try to resolve the real EC2 ID from the DB before proceeding.
                    if instance_id_for_action and not instance_id_for_action.startswith('i-'):
                        from backend.models.instance import Instance as _InstModel
                        _real = db.query(_InstModel).filter(
                            _InstModel.cluster_id == action.cluster_id,
                            _InstModel.node_name.like(f"{instance_id_for_action}%"),
                            _InstModel.instance_id.like('i-%'),
                        ).first()
                        if _real:
                            logger.info(
                                f"[auto_rebalancer] Resolved placeholder {instance_id_for_action} "
                                f"→ real EC2 ID {_real.instance_id}"
                            )
                            instance_id_for_action = _real.instance_id
                        else:
                            logger.error(
                                f"[auto_rebalancer] Action {action.id}: instance_id "
                                f"{instance_id_for_action} is not a real EC2 ID and no real "
                                f"record found — marking action as failed"
                            )
                            action.status = 'failed'
                            action.error_message = f"Placeholder instance_id {instance_id_for_action} has no real EC2 record"
                            db.commit()
                            return

                    # ── PRE-COMPUTE: karpenter_installed needed before ASG decrement ──
                    # Must determine Karpenter status early so the ASG pre-step can be
                    # gated on it.  The full NodePool-existence check happens later (line ~645)
                    # but we need a quick flag now.
                    _karpenter_precheck = getattr(cluster, 'karpenter_mode', None) is not None
                    if _karpenter_precheck:
                        try:
                            from backend.models.agent_action import AgentAction as _AA_PC, AgentActionType as _AAT_PC, AgentActionStatus as _AAS_PC
                            _karpenter_precheck = db.query(_AA_PC).filter(
                                _AA_PC.cluster_id == action.cluster_id,
                                _AA_PC.action_type == _AAT_PC.INSTALL_KARPENTER,
                                _AA_PC.status == _AAS_PC.COMPLETED,
                            ).first() is not None
                        except Exception:
                            pass

                    # ── PRE-STEP: ASG handling via helper module ──────────────────────
                    # Before draining the node, manage the ASG to prevent it from
                    # launching replacement on-demand nodes during the swap.
                    #
                    # For Karpenter path: reduce desired capacity so Karpenter sees
                    # pending pods and provisions spot.
                    #
                    # For direct EC2 launch (non-Karpenter): full ASG suspend/detach
                    # sequence to handle the last OD node safely. This suspends
                    # ReplaceUnhealthy/AZRebalance/Launch, lowers MinSize if needed,
                    # and detaches the instance with ShouldDecrementDesiredCapacity=True.
                    _asg_reduced = False
                    _asg_name_used = None
                    _asg_suspended = False
                    if instance_id_for_action and instance_id_for_action.startswith('i-'):
                        try:
                            from backend.utils.aws.asg import (
                                get_assumed_credentials,
                                get_asg_for_instance,
                                describe_auto_scaling_group,
                                suspend_asg_processes,
                                resume_asg_processes,
                                update_asg_min_size,
                            )
                            _region = cluster.region or "ap-south-1"
                            _asg_creds = get_assumed_credentials(cluster, db)

                            _asg_name = get_asg_for_instance(
                                instance_id_for_action, _region, _asg_creds
                            )

                            if _asg_name:
                                _asg_name_used = _asg_name

                                # ── SUSPEND ONLY — no capacity change here ──────────────
                                # We freeze the ASG so it cannot launch new OD nodes or
                                # replace "unhealthy" nodes while the swap is in progress.
                                # CRITICAL: we must NOT change DesiredCapacity or MinSize
                                # at this point. The cluster still needs all its nodes
                                # running until the new spot node is verified healthy and
                                # all pods have been drained from the target OD node.
                                #
                                # DesiredCapacity will be decremented exactly once — by the
                                # TERMINATE_NODE agent action (payload: decrement_asg=True)
                                # AFTER drain completes. That is the only safe moment to
                                # reduce cluster capacity.
                                _asg_suspended = suspend_asg_processes(
                                    _asg_name, _region, _asg_creds
                                )
                                logger.info(
                                    f"[auto_rebalancer] Suspended ASG '{_asg_name}' — "
                                    f"DesiredCapacity unchanged until after drain."
                                )

                                # Store current ASG config in metadata so Phase 2
                                # TERMINATE knows the baseline for its decrement.
                                try:
                                    _asg_info = describe_auto_scaling_group(
                                        _asg_name, _region, _asg_creds
                                    )
                                    if _asg_info:
                                        metadata.setdefault('asg_desired_at_start',
                                                            _asg_info["DesiredCapacity"])
                                        metadata.setdefault('asg_min_at_start',
                                                            _asg_info["MinSize"])
                                except Exception:
                                    pass
                            else:
                                logger.info(
                                    f"[auto_rebalancer] Instance {instance_id_for_action} not in any ASG "
                                    f"(may be Karpenter-managed) — skipping ASG handling"
                                )
                        except Exception as _asg_err:
                            logger.warning(
                                f"[auto_rebalancer] ASG pre-step failed for "
                                f"{instance_id_for_action}: {_asg_err} — continuing anyway"
                            )

                    # ── 2-PHASE PROVISION-AND-WAIT ─────────────────────────────────────
                    # Phase 1: Queue ONLY PATCH_KARPENTER_NODEPOOL.
                    #          This tells Karpenter to provision a new spot node.
                    #          Action resolution (below) waits for spot to be Ready.
                    # Phase 2: Once spot node is Ready, action resolution creates
                    #          CORDON → DRAIN → TERMINATE.
                    #
                    # This prevents the blast-radius problem where we drain a node
                    # BEFORE confirming a replacement exists.

                    ml_instance_types = [target_instance_type] if target_instance_type else ["t3.medium"]

                    # Determine required architectures from WorkloadInspector cache
                    _arch_values = ["amd64", "arm64"]  # default: allow both
                    try:
                        import json as _json_arch
                        from backend.core.redis_client import get_redis_client as _grc_arch
                        _arch_redis = _grc_arch()
                        _arch_raw = _arch_redis.get(f"spot:node_arch_constraints:{cluster.id}")
                        if _arch_raw:
                            _arch_map = _json_arch.loads(_arch_raw)
                            _node_archs = _arch_map.get(instance_id_for_action, [])
                            if _node_archs:
                                _arch_values = _node_archs
                    except Exception:
                        pass

                    # ── ALLOCATABLE CHECK: verify replacement ≥ current node's real capacity ──
                    try:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                        _cur_specs = _INSTANCE_VCPU_MEM.get(source_instance_type, (2, 8))
                        _tgt_specs = _INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
                        if _tgt_specs[0] < _cur_specs[0] or _tgt_specs[1] < _cur_specs[1]:
                            # Check if rightsizing is ON — only then allow downsizing
                            _opt_for_check = db.query(ClusterOptimizationSettings).filter(
                                ClusterOptimizationSettings.cluster_id == action.cluster_id
                            ).first()
                            if not (_opt_for_check and _opt_for_check.auto_rightsizing_enabled):
                                logger.warning(
                                    f"[auto_rebalancer] Rejecting {target_instance_type} "
                                    f"(vCPU={_tgt_specs[0]}, mem={_tgt_specs[1]}GB) — smaller than "
                                    f"current {source_instance_type} (vCPU={_cur_specs[0]}, mem={_cur_specs[1]}GB) "
                                    f"and rightsizing is OFF. Using same-size replacement."
                                )
                                target_instance_type = source_instance_type
                                ml_instance_types = [source_instance_type]
                    except Exception:
                        pass

                    try:
                        from backend.services.pool_ranking_service import PoolRankingService
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                        specs = _INSTANCE_VCPU_MEM.get(source_instance_type, (2, 8))
                        from backend.core.redis_client import get_redis_client as _grc_ml
                        _ranked_ml = PoolRankingService(db, _grc_ml()).rank_pools_for_size(
                            vcpu=specs[0], memory_gb=float(specs[1]),
                            region=cluster.region or "ap-south-1", limit=8
                        )
                        if _ranked_ml:
                            ml_instance_types = list(dict.fromkeys(
                                [p.pool.instance_type for p in _ranked_ml]
                            ))[:8] or ["t3a.medium", "t3.small", "t3.medium", "m6g.medium"]
                    except Exception:
                        pass

                    # ── PHASE 1: Provision spot node ────────────────────────────────
                    # CORDON, DRAIN, TERMINATE will be created by the action resolution
                    # step AFTER a spot node is confirmed Ready.
                    #
                    # Karpenter clusters:     PATCH_NODEPOOL AgentAction → agent applies it
                    #                         → Karpenter sees NodePool update → provisions spot
                    # Non-Karpenter clusters: Direct boto3 run_instances() spot launch
                    #                         → PATCH_NODEPOOL created as already-COMPLETED
                    #                         → Same 2-phase resolution loop awaits spot join
                    _phase1_payload = {
                        "nodepool_name": "default",
                        "instance_types": ml_instance_types,
                        "capacity_type": ["spot"],
                        "az": target_az,
                        "architecture": _arch_values,
                        "rebalancing_action_id": action.id,
                        "zero_downtime_step": 1,
                        # Phase 2 params so resolution can create CORDON/DRAIN/TERMINATE
                        "phase2_params": {
                            "instance_id": instance_id_for_action,
                            "instance_type": source_instance_type,
                            "az": source_az,
                        },
                    }

                    _karpenter_installed = getattr(cluster, 'karpenter_mode', None) is not None

                    # Fix 3: Before taking the Karpenter path, verify that a Karpenter
                    # install actually completed for this cluster (which creates the NodePool).
                    # If no INSTALL_KARPENTER action is COMPLETED, fall back to direct EC2 —
                    # patching a non-existent NodePool silently does nothing.
                    if _karpenter_installed:
                        try:
                            from backend.models.agent_action import AgentActionStatus as _AAS_P1
                            _install_completed = db.query(AgentAction).filter(
                                AgentAction.cluster_id == action.cluster_id,
                                AgentAction.action_type == AgentActionType.INSTALL_KARPENTER,
                                AgentAction.status == _AAS_P1.COMPLETED,
                            ).first()
                            if not _install_completed:
                                logger.warning(
                                    f"[auto_rebalancer] Phase 1: karpenter_mode set but no completed "
                                    f"INSTALL_KARPENTER for cluster {cluster.name} — NodePool may not "
                                    f"exist. Falling back to direct EC2 spot launch."
                                )
                                _karpenter_installed = False
                        except Exception as _kp_check_err:
                            logger.warning(
                                f"[auto_rebalancer] Phase 1: NodePool pre-check failed "
                                f"({_kp_check_err}) — proceeding with Karpenter path"
                            )

                    if _karpenter_installed:
                        # Karpenter path: queue AgentAction for in-cluster agent to process
                        nodepool_action = AgentAction(
                            cluster_id=action.cluster_id,
                            action_type=AgentActionType.PATCH_KARPENTER_NODEPOOL,
                            payload=_phase1_payload,
                        )
                        db.add(nodepool_action)
                        db.flush()
                        logger.info(
                            f"[auto_rebalancer] Phase 1 (Karpenter): queued PATCH_NODEPOOL "
                            f"(spot:{ml_instance_types[:3]}) — awaiting spot node. "
                            f"{source_instance_type}:{source_az}"
                        )
                    else:
                        # Non-Karpenter path: directly launch EC2 spot instance
                        # Track launch attempt for pool reliability metrics
                        try:
                            from backend.services.pool_ranking_service import report_launch_attempt as _rla
                            for _lt in ml_instance_types[:3]:
                                _rla(f"{_lt}:{target_az}")
                        except Exception:
                            pass

                        _new_ec2_id, _actual_itype, _actual_az = _launch_spot_instance_direct(
                            db, cluster,
                            source_instance_id=instance_id_for_action,
                            target_instance_types=ml_instance_types,
                            target_az=target_az,
                            region=cluster.region or "ap-south-1",
                        )
                        if not _new_ec2_id:
                            # Record launch failure for pool blacklist scoring
                            try:
                                from backend.services.pool_ranking_service import report_launch_failure as _rlf
                                for _lt in ml_instance_types[:3]:
                                    _rlf(f"{_lt}:{target_az}")
                            except Exception:
                                pass

                            # No capacity available for any type — fail cleanly
                            logger.error(
                                f"[auto_rebalancer] Action {action.id}: direct spot launch failed "
                                f"for cluster {cluster.name} — no capacity in any instance type"
                            )
                            action.status = 'failed'
                            action.error_message = (
                                "Direct spot EC2 launch failed: no spot capacity available "
                                f"for types {ml_instance_types[:3]}. Try again later."
                            )
                            db.commit()
                            return

                        # Update target_pool to the ACTUAL launched type (not just ML top pick)
                        if _actual_itype and _actual_az:
                            action.target_pool = f"{_actual_itype}:{_actual_az}"

                        # Create a pre-COMPLETED PATCH_NODEPOOL action so the resolution
                        # loop treats Phase 1 as done and waits for the spot node to join.
                        _phase1_payload["direct_ec2_launch"] = True
                        _phase1_payload["new_ec2_instance_id"] = _new_ec2_id
                        _phase1_payload["actual_instance_type"] = _actual_itype
                        # Fix 1: also store in RebalancingAction metadata so rollback
                        # helpers can find the orphan spot without a timestamp heuristic.
                        _meta_update_p1 = dict(action.action_metadata or {})
                        _meta_update_p1['replacement_spot_instance_id'] = _new_ec2_id
                        action.action_metadata = _meta_update_p1
                        from backend.models.agent_action import AgentActionStatus as _AAS_P1
                        nodepool_action = AgentAction(
                            cluster_id=action.cluster_id,
                            action_type=AgentActionType.PATCH_KARPENTER_NODEPOOL,
                            payload=_phase1_payload,
                            status=_AAS_P1.COMPLETED,
                            completed_at=datetime.utcnow(),
                        )
                        db.add(nodepool_action)
                        db.flush()
                        logger.info(
                            f"[auto_rebalancer] Phase 1 (direct EC2): launched spot {_new_ec2_id} "
                            f"— waiting for it to join cluster {cluster.name} as a K8s node. "
                            f"Phase 2 (CORDON→DRAIN→TERMINATE {instance_id_for_action}) starts after join."
                        )

                    # Set 24h cooldown on this instance immediately so the rebalancer
                    # doesn't re-target it in the next cycle while agent actions are in-flight.
                    if instance_id_for_action:
                        try:
                            _cooldown_key = f"spot:rebalanced:instance:{instance_id_for_action}"
                            _redis.setex(_cooldown_key, 86400, "1")
                            logger.info(
                                f"[auto_rebalancer] Set 24h cooldown for instance {instance_id_for_action}"
                            )
                        except Exception as _cd_err:
                            logger.warning(f"[auto_rebalancer] Failed to set instance cooldown: {_cd_err}")

            except RuntimeError as lock_err:
                logger.warning(f"[auto_rebalancer] Action {action.id} deferred: lock contention — {lock_err}")
                action.status = 'deferred'
                action.error_message = f"Lock contention: {lock_err}"
                db.commit()
                return

            # Mark as waiting_agent — actual completion tracked in Step 0 of main task loop
            # when all 4 associated AgentActions reach COMPLETED/FAILED status.
            action.status = 'waiting_agent'
            action.nodes_affected = 1
            # Issue 4 fix: count real pods from pod_metrics instead of hardcoded 3.
            # Phase 2 hasn't run yet so this is a pre-drain estimate; updated to 0 if no data.
            try:
                from backend.models.pod_metric import PodMetric
                _target_node_inst = db.query(Instance).filter(
                    Instance.instance_id == instance_id_for_action
                ).first()
                _target_node_name = _target_node_inst.node_name if _target_node_inst else None
                if _target_node_name:
                    from datetime import timedelta
                    _recent_cutoff = datetime.utcnow() - timedelta(minutes=10)
                    action.pods_migrated = db.query(PodMetric.pod_name).filter(
                        PodMetric.node_name == _target_node_name,
                        PodMetric.timestamp >= _recent_cutoff,
                    ).distinct().count()
                else:
                    action.pods_migrated = 0
            except Exception:
                action.pods_migrated = 0
            # Persist ASG state for Phase 2 resume
            _meta_update = dict(action.action_metadata or {})
            if _asg_name_used:
                _meta_update['asg_name_used'] = _asg_name_used
            if _asg_suspended:
                _meta_update['asg_suspended'] = True
            # Record spot baseline BEFORE Phase 1 launched.
            # Phase 2 trigger uses this to detect that a NEW spot node joined —
            # not just any pre-existing spot instance from a concurrent rebalance.
            try:
                _spot_baseline = db.query(Instance).filter(
                    Instance.cluster_id == action.cluster_id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state == 'running',
                ).count()
                _meta_update['spot_baseline_count'] = _spot_baseline
            except Exception:
                _meta_update['spot_baseline_count'] = 0
            action.action_metadata = _meta_update
            db.commit()

            logger.info(
                f"[auto_rebalancer] Action {action.id} queued 4 agent steps — "
                f"status=waiting_agent until agent completes PATCH_NODEPOOL→CORDON→DRAIN→TERMINATE"
            )

        except Exception as e:
            logger.error(f"Failed to execute rebalancing action {action.id}: {e}")
            # Resume ASG if it was suspended before the exception.
            # action_metadata is committed immediately after ASG suspend, so we can read it here.
            _err_meta = dict(action.action_metadata or {})
            if _err_meta.get('asg_suspended') and _err_meta.get('asg_name_used'):
                try:
                    from backend.utils.aws.asg import resume_asg_processes as _rasp_err
                    from backend.utils.aws.asg import get_assumed_credentials as _gac_err
                    from backend.models.system_config import SystemConfig as _SC_err
                    _cl_err = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
                    if _cl_err:
                        _rgn_err = _cl_err.region or "ap-south-1"
                        _pk_err = db.query(_SC_err).filter(_SC_err.key == "PLATFORM_AWS_ACCESS_KEY").first()
                        _ps_err = db.query(_SC_err).filter(_SC_err.key == "PLATFORM_AWS_SECRET").first()
                        if _pk_err and _ps_err:
                            _base_err = {"aws_access_key_id": _pk_err.value, "aws_secret_access_key": _ps_err.value}
                            _creds_err = _gac_err(_cl_err.aws_role_arn, _rgn_err, **_base_err) if _cl_err.aws_role_arn else _base_err
                            _rasp_err(_err_meta['asg_name_used'], _rgn_err, _creds_err)
                            logger.info(f"[auto_rebalancer] Resumed ASG '{_err_meta['asg_name_used']}' after exception on action {action.id}")
                except Exception as _asg_resume_err:
                    logger.error(f"[auto_rebalancer] Failed to resume ASG '{_err_meta.get('asg_name_used')}' after exception: {_asg_resume_err}")
            action.status = 'failed'
            action.completed_at = datetime.utcnow()
            action.duration_seconds = int((action.completed_at - action.started_at).total_seconds()) if action.started_at else 0
            action.error_message = str(e)
            db.commit()

def trigger_graceful_rebalancing(
    cluster_id: str,
    source_pool: str,
    target_pool: str,
    reason: str = "proactive_optimization",
    instance_id: str = None,
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
                'initiated_by': 'system',
                **({"instance_id": instance_id} if instance_id else {}),
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


def _seed_instances_from_redis(db: Session, cluster) -> list:
    """
    When the `instances` table has no records for this cluster (agent-reported nodes
    haven't been persisted yet), seed synthetic Instance rows from Redis node telemetry
    so the auto-rebalancer has something to work with.

    Uses capacity data to infer instance type.  Synthetic instance_ids are derived from
    the node hostname's IP component (e.g. 'ip-192-168-14-254'), which fits VARCHAR(20).
    Lifecycle is assumed ON_DEMAND (the rebalancer will migrate them to spot).
    """
    from backend.core.redis_client import get_redis_client as _grc
    from backend.models.instance import Instance
    import ast as _ast
    import json as _json

    _TYPE_MAP = [
        (2, 0.5, "t3.nano"), (2, 1.0, "t3.micro"), (2, 2.0, "t3.small"),
        (2, 4.0, "t3.medium"), (2, 8.0, "t3.large"), (4, 16.0, "t3.xlarge"),
        (8, 32.0, "t3.2xlarge"),
        (2, 8.0, "m5.large"), (4, 16.0, "m5.xlarge"), (8, 32.0, "m5.2xlarge"),
        (2, 4.0, "c5.large"), (4, 8.0, "c5.xlarge"),
        (2, 16.0, "r5.large"), (4, 32.0, "r5.xlarge"),
    ]

    def _infer_type(vcpu, mem_gb):
        best, best_dist = "t3.medium", 1e9
        for v, m, name in _TYPE_MAP:
            dist = abs(v - vcpu) * 8 + abs(m - mem_gb)
            if dist < best_dist:
                best_dist, best = dist, name
        return best

    _redis = _grc()
    _pattern = f"metrics:node:{cluster.id}:*"
    try:
        # Issue 13 fix: use scan_iter instead of keys() — avoids O(N) blocking scan
        _keys = list(_redis.scan_iter(_pattern))
    except Exception:
        return []

    seeded = []
    for _key in _keys:
        try:
            _raw = _redis.get(_key)
            if not _raw:
                continue
            _raw_str = _raw.decode('utf-8') if isinstance(_raw, bytes) else str(_raw)
            try:
                _data = _json.loads(_raw_str)
            except Exception:
                try:
                    _data = _ast.literal_eval(_raw_str)
                except Exception:
                    continue

            node_name = _data.get('node_name', '')
            # Extract ip-xxx-xxx-xxx-xxx from hostname (fits VARCHAR(20))
            _short_id = node_name.split('.')[0] if node_name else ''
            if not _short_id or len(_short_id) > 20:
                _short_id = node_name[:20]
            if not _short_id:
                continue

            # Skip if already exists
            existing = db.query(Instance).filter(Instance.instance_id == _short_id).first()
            if existing:
                if existing.lifecycle == InstanceLifecycle.ON_DEMAND:
                    seeded.append(existing)
                continue

            cpu_mc = _data.get('cpu_capacity_millicores', 2000)
            mem_bytes = _data.get('memory_capacity_bytes', 4026089472)
            vcpu = max(1, round(cpu_mc / 1000))
            mem_gb = round(mem_bytes / (1024 ** 3), 1)
            itype = _infer_type(vcpu, mem_gb)

            new_inst = Instance(
                cluster_id=cluster.id,
                instance_id=_short_id,
                instance_type=itype,
                lifecycle=InstanceLifecycle.ON_DEMAND,
                az=f"{cluster.region or 'ap-south-1'}a",
                price=0.0,  # real price populated by pricing_collector worker
                cpu_util=round(
                    _data.get('cpu_usage_millicores', 0) / max(cpu_mc, 1) * 100, 1
                ),
                memory_util=round(
                    _data.get('memory_usage_bytes', 0) / max(mem_bytes, 1) * 100, 1
                ),
                state='running',
                status='READY',
                architecture='amd64',
            )
            db.add(new_inst)
            seeded.append(new_inst)
            logger.info(
                f"[auto_rebalancer] Seeded instance {_short_id} ({itype}) "
                f"for cluster {cluster.name} from Redis telemetry"
            )
        except Exception as _e:
            logger.warning(f"[auto_rebalancer] Failed to seed node from Redis key {_key}: {_e}")

    if seeded:
        try:
            db.commit()
        except Exception as _ce:
            db.rollback()
            logger.warning(f"[auto_rebalancer] Failed to commit seeded instances: {_ce}")
            seeded = []

    return seeded


# ── Rollback helpers ─────────────────────────────────────────────────────────
# Shared by CORDON failure, DRAIN failure, and EC2-terminate failure paths.

def _do_rollback_uncordon_and_terminate(wa, wa_meta, db):
    """
    Full rollback after a pre-drain failure (CORDON failed or similar):
      1. Resume suspended ASG processes so the cluster is not frozen.
      2. Queue UNCORDON_NODE so the old OD node is schedulable again.
      3. Terminate the orphan spot instance that was launched for this cycle.

    Never raises — all steps wrapped in try/except.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # 1. Resume ASG
    _rb_asg = wa_meta.get('asg_name_used')
    if _rb_asg:
        try:
            from backend.utils.aws.asg import (
                get_assumed_credentials as _gac_rb_uat,
                resume_asg_processes as _rap_rb_uat,
            )
            _rb_cluster_uat = db.query(Cluster).filter(Cluster.id == wa.cluster_id).first()
            if _rb_cluster_uat:
                _rb_creds_uat = _gac_rb_uat(_rb_cluster_uat, db)
                _rap_rb_uat(_rb_asg, _rb_cluster_uat.region or "ap-south-1", _rb_creds_uat)
                logger.info(f"[rollback] Resumed ASG '{_rb_asg}' (action {wa.id})")
        except Exception as _e:
            logger.warning(f"[rollback] ASG resume failed: {_e}")

    # 2. Queue UNCORDON_NODE
    _rb_node = wa_meta.get('target_node_name') or wa_meta.get('node_name')
    if _rb_node:
        try:
            _unc = AgentAction(
                cluster_id=wa.cluster_id,
                action_type=AgentActionType.UNCORDON_NODE,
                status=AgentActionStatus.PENDING,
                payload={"node_name": _rb_node},
                action_metadata={"rollback_for_action_id": str(wa.id)},
            )
            db.add(_unc)
            db.commit()
            logger.info(f"[rollback] Queued UNCORDON_NODE for {_rb_node} (action {wa.id})")
        except Exception as _e:
            logger.error(f"[rollback] UNCORDON_NODE queue failed: {_e}")

    # 3. Terminate orphan spot
    _do_rollback_terminate_orphan_spot(wa, wa_meta, db)


def _do_rollback_terminate_orphan_spot(wa, wa_meta, db):
    """
    Terminate the replacement spot instance launched for a failed rebalancing cycle.
    Prefers wa_meta['replacement_spot_instance_id'] (stored at Phase 1 launch);
    falls back to timestamp query (latest SPOT created after action start).

    Never raises — wrapped in try/except.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    try:
        _rb_cluster = db.query(Cluster).filter(Cluster.id == wa.cluster_id).first()
        if not _rb_cluster:
            return

        # Prefer explicit instance_id stored at launch time
        _orphan_id = wa_meta.get('replacement_spot_instance_id')
        _orphan_inst = None

        if _orphan_id:
            _orphan_inst = db.query(Instance).filter(
                Instance.cluster_id == _rb_cluster.id,
                Instance.instance_id == _orphan_id,
            ).first()

        if not _orphan_inst:
            # Fallback: newest SPOT created since this action started
            _orphan_inst = (
                db.query(Instance)
                .filter(
                    Instance.cluster_id == _rb_cluster.id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.created_at >= wa.created_at,
                )
                .order_by(Instance.created_at.desc())
                .first()
            )

        if _orphan_inst and _orphan_inst.instance_id:
            from backend.utils.aws.asg import get_assumed_credentials as _gac_spot
            import boto3 as _b3spot
            _spot_creds = _gac_spot(_rb_cluster, db)
            _spot_ec2 = _b3spot.Session(
                aws_access_key_id=_spot_creds.get('AccessKeyId'),
                aws_secret_access_key=_spot_creds.get('SecretAccessKey'),
                aws_session_token=_spot_creds.get('SessionToken'),
            ).client("ec2", region_name=_rb_cluster.region or "ap-south-1")
            _spot_ec2.terminate_instances(InstanceIds=[_orphan_inst.instance_id])
            logger.info(
                f"[rollback] Terminated orphan spot {_orphan_inst.instance_id} "
                f"(action {wa.id})"
            )
            wa_meta['rollback_terminated_spot'] = _orphan_inst.instance_id
            wa.action_metadata = wa_meta
            db.commit()
        else:
            logger.info(f"[rollback] No orphan spot instance found for action {wa.id}")
    except Exception as _e:
        logger.warning(f"[rollback] Orphan spot terminate failed (action {wa.id}): {_e}")


# Celery task registration
from backend.workers.app import app

@app.task(name='workers.auto_rebalancer')
def execute_rebalancing():
    """Celery task entry point for auto-rebalancing."""
    logger.info("Auto-rebalancer task started")

    db = next(get_db())

    try:
        from backend.core.redis_client import get_redis_client as _get_redis_outer
        _redis = _get_redis_outer()
    except Exception:
        _redis = None

    try:
        # Step 0: Resolve waiting_agent actions whose AgentActions have all finished.
        # An action stays 'waiting_agent' until PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE
        # all complete on the agent. This prevents UI showing "completed" prematurely.
        from backend.models.agent_action import AgentAction as _AA0, AgentActionStatus as _AAS0
        waiting_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status == 'waiting_agent'
        ).all()
        for _wa in waiting_actions:
            try:
                _still_pending = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                    _AA0.status.in_([_AAS0.PENDING, _AAS0.PICKED_UP])
                ).count()
                if _still_pending > 0:
                    # ── STEP TRACKING: record step timestamps while agent is still working ──
                    _wa_meta_live = dict(_wa.action_metadata or {})
                    from backend.models.agent_action import AgentActionType as _AAT0
                    for _sname, _stype in [
                        ('step_1_spot_provisioning', _AAT0.PATCH_KARPENTER_NODEPOOL),
                        ('step_2_cordon', _AAT0.CORDON_NODE),
                        ('step_3_draining_pods', _AAT0.DRAIN_NODE),
                    ]:
                        if _sname not in _wa_meta_live:
                            _sa = db.query(_AA0).filter(
                                _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                                _AA0.action_type == _stype,
                                _AA0.status == _AAS0.COMPLETED,
                            ).first()
                            if _sa and _sa.completed_at:
                                _wa_meta_live[_sname] = _sa.completed_at.isoformat()
                    # Determine current_step from what's done so far
                    if 'step_3_draining_pods' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'waiting_for_spot_node'
                    elif 'step_2_cordon' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'draining_pods'
                    elif 'step_1_spot_provisioning' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'cordoning_node'
                    else:
                        _wa_meta_live['current_step'] = 'provisioning_spot_pool'
                    _wa.action_metadata = _wa_meta_live
                    db.commit()
                    continue  # Agent still working — leave as waiting_agent

                _failed = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                    _AA0.status == _AAS0.FAILED
                ).count()

                _wa_meta = dict(_wa.action_metadata or {})
                _wa_instance_id = _wa_meta.get("instance_id", "")

                # ── Record step timestamps for completed agent actions ────────
                from backend.models.agent_action import AgentActionType as _AAT0
                for _sname, _stype in [
                    ('step_1_spot_provisioning', _AAT0.PATCH_KARPENTER_NODEPOOL),
                    ('step_2_cordon', _AAT0.CORDON_NODE),
                    ('step_3_draining_pods', _AAT0.DRAIN_NODE),
                ]:
                    if _sname not in _wa_meta:
                        _sa = db.query(_AA0).filter(
                            _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                            _AA0.action_type == _stype,
                        ).first()
                        if _sa:
                            ts = (_sa.completed_at or _sa.created_at)
                            if ts:
                                _wa_meta[_sname] = ts.isoformat()

                # ── 2-PHASE: WAIT FOR SPOT NODE → CREATE PHASE 2 ACTIONS ──────
                # After PATCH_NODEPOOL completes (Phase 1), wait for a spot node
                # to be Ready BEFORE creating CORDON/DRAIN/TERMINATE (Phase 2).
                # This prevents draining when no replacement exists.
                # NOTE: This block is intentionally OUTSIDE the 'for _sname, _stype' loop
                # above. Previously it was incorrectly indented inside the loop, causing
                # `continue` to only advance the inner loop instead of the outer `for _wa`
                # loop — all 3 iterations completed with `continue`, then execution fell
                # through to the EC2 terminate block, immediately killing the OD node
                # without waiting for the spot replacement to join.
                if _failed == 0:
                    _wa_cluster_obj = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                    # Fix 1: Use payload-based Karpenter detection — live karpenter_mode can
                    # change between Phase 1 execution and Phase 2 resolution (race condition).
                    # If karpenter_mode flips to null between execution and resolution, the old
                    # live check gives _wa_karpenter_active=False, bypasses the spot wait, and
                    # creates Phase 2 (CORDON→DRAIN→TERMINATE) immediately — destroying the node
                    # before a spot replacement joins.  Reading the Phase 1 payload is stable.
                    _patch_sa_check = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.PATCH_KARPENTER_NODEPOOL,
                    ).first()
                    _direct_launch = bool(
                        _patch_sa_check and
                        (_patch_sa_check.payload or {}).get("direct_ec2_launch")
                    )
                    # Karpenter path was used if Phase 1 payload has nodepool_name (not direct EC2)
                    _karpenter_from_payload = bool(
                        _patch_sa_check and
                        (_patch_sa_check.payload or {}).get("nodepool_name") and
                        not _direct_launch
                    )
                    # Wait for spot if: Karpenter path was used (stable payload flag), OR direct EC2 launched
                    _wa_karpenter_active = _karpenter_from_payload or _direct_launch

                    _spot_count = db.query(Instance).filter(
                        Instance.cluster_id == _wa.cluster_id,
                        Instance.lifecycle == InstanceLifecycle.SPOT,
                        Instance.state == 'running',
                    ).count()

                    # Use the baseline recorded at Phase 1 creation time.
                    # This ensures we wait for a NEW spot node to join for THIS specific
                    # rebalancing action — not a pre-existing spot from another concurrent action.
                    _spot_baseline = int(_wa_meta.get('spot_baseline_count', 0))
                    _new_spot_joined = False
                    if _spot_count > _spot_baseline:
                        # NEW spot instance joined — but also require it has been running for
                        # at least 90 seconds so EC2 status checks pass and the node can register
                        # with K8s before we drain the OD node underneath it.
                        _newest_spot = db.query(Instance).filter(
                            Instance.cluster_id == _wa.cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                        ).order_by(Instance.created_at.desc()).first()
                        _SPOT_STABILIZE_S = 90
                        _spot_age_s = (
                            (datetime.utcnow() - _newest_spot.created_at).total_seconds()
                            if (_newest_spot and _newest_spot.created_at) else 0
                        )
                        if _spot_age_s >= _SPOT_STABILIZE_S and _newest_spot.node_name:
                            _new_spot_joined = True
                            # Fix 1: store replacement spot ID for reliable rollback
                            if _newest_spot.instance_id and not _wa_meta.get('replacement_spot_instance_id'):
                                _wa_meta['replacement_spot_instance_id'] = _newest_spot.instance_id
                                _wa.action_metadata = _wa_meta
                            # Issue 3 fix: store node_name in metadata so we don't rely on
                            # _newest_spot variable which may hold stale data from a prior loop iteration
                            if _newest_spot.node_name and not _wa_meta.get('replacement_spot_node_name'):
                                _wa_meta['replacement_spot_node_name'] = _newest_spot.node_name
                                _wa.action_metadata = _wa_meta
                        elif _spot_age_s >= _SPOT_STABILIZE_S and not _newest_spot.node_name:
                            logger.debug(
                                f"[auto_rebalancer] Action {_wa.id}: new spot EC2 up "
                                f"{int(_spot_age_s)}s but node_name not set yet (kubelet not joined k8s) — waiting"
                            )
                        else:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: new spot appeared but "
                                f"only {int(_spot_age_s)}s old (need {_SPOT_STABILIZE_S}s) — "
                                f"waiting for node to stabilize before Phase 2"
                            )

                    # Check if Phase 2 actions exist yet
                    _phase2_exists = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                    ).count() > 0

                    # Measure elapsed since PATCH_NODEPOOL completed
                    _patch_sa = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.PATCH_KARPENTER_NODEPOOL,
                        _AA0.status == _AAS0.COMPLETED,
                    ).first()
                    _patch_completed_at = (_patch_sa.completed_at if _patch_sa else None) or _wa.started_at
                    _spot_wait_elapsed = (
                        (datetime.utcnow() - _patch_completed_at).total_seconds()
                        if _patch_completed_at else 9999
                    )
                    _SPOT_WAIT_TIMEOUT_S = 30 * 60  # 30 minutes

                    # ── Phase 2 creation: NEW spot joined OR timeout ───────────
                    if not _phase2_exists:
                        if _wa_karpenter_active and not _new_spot_joined and _spot_wait_elapsed < _SPOT_WAIT_TIMEOUT_S:
                            # Still waiting for THIS action's spot replacement — do NOT create drain actions yet
                            _wa_meta['current_step'] = 'waiting_for_spot_node'
                            _wa_meta['spot_wait_elapsed_s'] = int(_spot_wait_elapsed)
                            _wa_meta['spot_count_current'] = _spot_count
                            _wa_meta['spot_count_baseline'] = _spot_baseline
                            _wa_meta['provisioner_type'] = 'karpenter' if _karpenter_from_payload else 'agent'
                            _wa.action_metadata = _wa_meta
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 1 done, "
                                f"waiting for NEW spot node (current={_spot_count}, baseline={_spot_baseline}, "
                                f"{int(_spot_wait_elapsed)}s elapsed, timeout {_SPOT_WAIT_TIMEOUT_S}s)"
                            )
                            db.commit()
                            continue  # Re-check next cycle (outer for _wa loop)

                        if _new_spot_joined:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: NEW spot node joined! "
                                f"(count {_spot_baseline} → {_spot_count}) "
                                f"Creating Phase 2 actions (CORDON→DRAIN→TERMINATE)"
                            )
                            _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()

                            # Apply karpenter.sh/do-not-disrupt=true to the new spot node.
                            # This prevents Karpenter's consolidation/expiry loop from
                            # terminating the replacement node while pods are still draining
                            # onto it.  The annotation is removed after Phase 2 completes.
                            if _newest_spot and _newest_spot.node_name:
                                try:
                                    from backend.models.agent_action import AgentAction as _AA_ANN, AgentActionType as _AAT_ANN, AgentActionStatus as _AAS_ANN
                                    _kp_annotate = _AA_ANN(
                                        cluster_id=_wa.cluster_id,
                                        action_type=_AAT_ANN.LABEL_NODE,
                                        status=_AAS_ANN.PENDING,
                                        payload={
                                            "node_name": _newest_spot.node_name,
                                            "labels": {},
                                            "annotations": {
                                                "karpenter.sh/do-not-disrupt": "true"
                                            },
                                        },
                                        action_metadata={"rebalancing_action_id": str(_wa.id),
                                                         "purpose": "protect_replacement_node"},
                                    )
                                    db.add(_kp_annotate)
                                    db.flush()
                                    logger.info(
                                        f"[auto_rebalancer] Queued karpenter.sh/do-not-disrupt=true "
                                        f"on {_newest_spot.node_name} (action {_wa.id})"
                                    )
                                except Exception as _ann_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Failed to queue do-not-disrupt annotation: {_ann_err}"
                                    )
                        elif _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S and _wa_karpenter_active:
                            # Karpenter timeout: Karpenter was supposed to provision but didn't.
                            # Safety check: only proceed if other nodes exist to absorb workloads.
                            # Draining without any running replacement onto a single-node cluster
                            # causes guaranteed downtime — fail cleanly instead.
                            _other_running = db.query(Instance).filter(
                                Instance.cluster_id == _wa.cluster_id,
                                Instance.state == 'running',
                                Instance.instance_id != _wa_instance_id,
                            ).count()
                            if _other_running == 0:
                                logger.error(
                                    f"[auto_rebalancer] Action {_wa.id}: Karpenter timeout AND "
                                    f"no other nodes in cluster — refusing to drain last node "
                                    f"without a replacement."
                                )
                                _wa.status = 'failed'
                                _wa.error_message = (
                                    "Karpenter spot provisioning timed out and no other cluster "
                                    "nodes exist. Drain aborted to prevent workload downtime. "
                                    "Check Karpenter logs and EC2 spot capacity for this region."
                                )
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                db.commit()
                                continue
                            # Other nodes exist — pods can reschedule if Karpenter doesn't provision.
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: Karpenter spot wait timeout "
                                f"({int(_spot_wait_elapsed)}s) but {_other_running} other node(s) "
                                f"available. Proceeding with drain — Karpenter should provision after."
                            )
                        elif _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S and not _wa_karpenter_active:
                            # No Karpenter + no spot node = nothing will ever provision a replacement.
                            # FAIL the action cleanly. Do not drain or terminate the OD node.
                            logger.error(
                                f"[auto_rebalancer] Action {_wa.id}: no spot node joined after "
                                f"{int(_spot_wait_elapsed)}s and Karpenter is not installed. "
                                f"Failing action — cannot replace OD node without a replacement."
                            )
                            _wa.status = 'failed'
                            _wa.error_message = (
                                "Spot wait timeout: no replacement spot node joined the cluster. "
                                "Check spot capacity availability in this region/AZ, or enable "
                                "Karpenter for automatic spot provisioning with fallback logic."
                            )
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            db.commit()
                            continue  # outer for _wa loop

                        # ── CREATE PHASE 2 ACTIONS ────────────────────────────
                        # Retrieve instance params stored in Phase 1 payload
                        _p1_payload = _patch_sa.payload if _patch_sa else {}
                        _p2 = _p1_payload.get("phase2_params", {})
                        _p2_instance_id = _p2.get("instance_id") or _wa_meta.get("instance_id", "")
                        _p2_instance_type = _p2.get("instance_type", "")
                        _p2_az = _p2.get("az", "")

                        if _p2_instance_id:
                            from backend.models.agent_action import AgentAction as _AA_P2
                            cordon_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.CORDON_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 2,
                                }
                            )
                            drain_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.DRAIN_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "ignore_daemonsets": True,
                                    "grace_period_seconds": 60,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 3,
                                }
                            )
                            terminate_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.TERMINATE_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "node_name": None,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 4,
                                    "decrement_asg": True,
                                    # Pass ASG context so agent can reduce MinSize if
                                    # needed before decrementing DesiredCapacity.
                                    "asg_name": _wa_meta.get("asg_name_used"),
                                    "asg_min_at_start": _wa_meta.get("asg_min_at_start"),
                                    "asg_desired_at_start": _wa_meta.get("asg_desired_at_start"),
                                }
                            )
                            db.add(cordon_p2)
                            db.add(drain_p2)
                            db.add(terminate_p2)
                            db.flush()
                            _wa_meta['current_step'] = 'cordoning_node'
                            _wa_meta['phase2_created_at'] = datetime.utcnow().isoformat()
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 2 created "
                                f"(CORDON→DRAIN→TERMINATE for {_p2_instance_id})"
                            )
                        continue  # Wait for Phase 2 to complete (outer for _wa loop)

                    # Phase 2 exists — check if drain is done, wait for completion
                    _drain_sa = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.COMPLETED,
                    ).first()
                    if 'step_3_draining_pods' not in _wa_meta and _drain_sa and _drain_sa.completed_at:
                        _wa_meta['step_3_draining_pods'] = _drain_sa.completed_at.isoformat()

                    # ── READINESS-AWARE VERIFICATION ────────────────────────────────────
                    # After all K8s steps complete (CORDON → DRAIN → kubectl delete node),
                    # enforce a 90-second grace period before EC2 termination.
                    # This gives evicted pods time to reschedule on the replacement spot node.
                    # Max wait: 5 minutes. Pods stuck after 5 min → log warning and proceed
                    # (K8s node is already deleted; uncordon is not possible at this stage).
                    if not _wa_meta.get('readiness_verified'):
                        _post_drain_ts = _wa_meta.get('post_drain_readiness_started_at')
                        if not _post_drain_ts:
                            # First cycle after K8s actions complete: start readiness timer
                            _wa_meta['post_drain_readiness_started_at'] = datetime.utcnow().isoformat()
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        _post_drain_elapsed = (
                            datetime.utcnow() - datetime.fromisoformat(_post_drain_ts)
                        ).total_seconds()
                        _READINESS_GRACE_S = 90   # 90 seconds minimum after kubectl delete node
                        _READINESS_MAX_S   = 300  # 5-minute maximum wait

                        if _post_drain_elapsed < _READINESS_GRACE_S:
                            # Still in grace period — wait for next cycle
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa_meta['post_drain_elapsed_s'] = int(_post_drain_elapsed)
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        # Grace period passed: check pod_metrics for pods still on old node
                        _drained_inst_rd = _wa_meta.get('instance_id', '')
                        _pods_stuck = False
                        if _drained_inst_rd:
                            try:
                                from backend.models.pod_metric import PodMetric as _PM_RD
                                _pods_stuck = db.query(_PM_RD).filter(
                                    _PM_RD.cluster_id == _wa.cluster_id,
                                    _PM_RD.node_name == _drained_inst_rd,
                                    _PM_RD.timestamp >= datetime.utcnow() - timedelta(minutes=2),
                                ).count() > 0
                            except Exception:
                                pass  # pod_metrics unavailable — proceed optimistically

                        if _pods_stuck and _post_drain_elapsed < _READINESS_MAX_S:
                            # Pods still migrating — wait up to 5 min total
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa_meta['post_drain_elapsed_s'] = int(_post_drain_elapsed)
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        if _pods_stuck and _post_drain_elapsed >= _READINESS_MAX_S:
                            # 5-min timeout: pods may still be stuck but the K8s node object
                            # was already deleted by the drain sequence — uncordon is not
                            # meaningful at this point (there is nothing to uncordon).
                            # Log the anomaly and proceed to EC2 terminate.
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: pod readiness timeout "
                                f"({int(_post_drain_elapsed)}s) — pods may still be on "
                                f"{_drained_inst_rd}. K8s node already deleted; "
                                f"proceeding to EC2 terminate."
                            )

                        # Readiness verified (grace period elapsed, no stuck pods or timeout)
                        _wa_meta['readiness_verified'] = True
                        _wa_meta['readiness_verified_at'] = datetime.utcnow().isoformat()
                        _wa.action_metadata = _wa_meta
                        db.commit()

                    # Spot appeared or timeout reached — record and proceed to terminate
                    if _spot_count > 0:
                        _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()
                        _wa_meta['current_step'] = 'old_node_terminating'
                    else:
                        _wa_meta['current_step'] = 'old_node_terminating_timeout'
                        logger.warning(
                            f"[auto_rebalancer] Action {_wa.id}: spot node wait timeout "
                            f"({int(_spot_wait_elapsed)}s) — proceeding to terminate old OD node anyway"
                        )

                # Fix 2 + CORDON guard: if ANY Phase 2 action failed, determine which
                # stage failed and execute the appropriate rollback.
                if _failed > 0:
                    # ── CORDON failure: drain never ran — full clean rollback ────────
                    _cordon_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    # Also check whether drain ran (to distinguish cordon-only failure)
                    _drain_attempted = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                    ).count() > 0

                    if _cordon_node_failed and not _drain_attempted:
                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: CORDON_NODE failed — "
                            f"rolling back (uncordon + terminate orphan spot). "
                            f"Clearing cooldown for retry."
                        )
                        _wa.status = 'failed'
                        _wa.error_message = (
                            f"CORDON_NODE failed. Node {_wa_instance_id} unchanged. "
                            f"Orphan spot instance terminated. Will retry next cycle."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'failed_cordon_rollback'
                        _wa.action_metadata = _wa_meta
                        if _wa_instance_id and _redis:
                            try:
                                _redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")
                            except Exception:
                                pass
                        db.commit()
                        _do_rollback_uncordon_and_terminate(_wa, _wa_meta, db)
                        continue

                    # ── DRAIN failure: workloads still on old node — safe rollback ──
                    _drain_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    if _drain_node_failed:
                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: DRAIN_NODE failed — "
                            f"EC2 terminate SKIPPED to protect workloads on {_wa_instance_id}. "
                            f"Clearing per-instance cooldown for retry."
                        )
                        _wa.status = 'failed'
                        _wa.error_message = (
                            f"DRAIN_NODE failed (conflict or pod disruption budget). "
                            f"EC2 terminate skipped — {_wa_instance_id} still running. "
                            f"Cooldown cleared; rebalancer will retry on next cycle."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'failed_drain_ec2_protected'
                        _wa.action_metadata = _wa_meta
                        if _wa_instance_id and _redis:
                            try:
                                _redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")
                            except Exception:
                                pass
                        db.commit()
                        # Full rollback via shared helper:
                        # 1. Resume ASG (unfreeze cluster)
                        # 2. Queue UNCORDON_NODE (undo cordon on old OD node)
                        # 3. Terminate orphan spot instance
                        _do_rollback_uncordon_and_terminate(_wa, _wa_meta, db)
                        continue

                # ── Backend EC2 terminate: drain is done, now kill the instance ──
                # Agent's kubectl delete node removes the K8s object but leaves EC2
                # running. We must terminate via backend's assumed IAM role to ensure
                # the instance is actually gone so Karpenter provisions a spot replacement.
                if _wa_instance_id and _wa_instance_id.startswith("i-") and _failed == 0:
                    try:
                        import boto3 as _b3wa
                        from backend.models.system_config import SystemConfig as _SC
                        _wa_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                        _wa_region  = (_wa_cluster.region if _wa_cluster else None) or "ap-south-1"

                        # Load stored platform credentials (same pattern as _sync_instance_state_from_aws)
                        _pk_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_ACCESS_KEY").first()
                        _ps_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_SECRET").first()
                        _pr_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_REGION").first()
                        _plat_key    = (_pk_row.value if _pk_row and _pk_row.value else None)
                        _plat_secret = (_ps_row.value if _ps_row and _ps_row.value else None)
                        _plat_region = (_pr_row.value if _pr_row and _pr_row.value else None) or _wa_region

                        _wa_creds = {}
                        # Resolve IAM role ARN: cluster-level → account-level → no assumption
                        _wa_role_arn = (_wa_cluster.aws_role_arn if _wa_cluster else None)
                        _wa_ext_id   = (_wa_cluster.aws_external_id if _wa_cluster else None)
                        if not _wa_role_arn and _wa_cluster and _wa_cluster.account_id:
                            try:
                                from backend.models.account import Account as _Acct
                                _acct = db.query(_Acct).filter(_Acct.id == _wa_cluster.account_id).first()
                                if _acct:
                                    _wa_role_arn = _acct.role_arn
                                    _wa_ext_id   = _acct.external_id
                            except Exception:
                                pass

                        if _wa_role_arn and _plat_key and _plat_secret:
                            # Use stored platform credentials to build the STS client, then assume role
                            _sts_wa = _b3wa.client("sts",
                                                   aws_access_key_id=_plat_key,
                                                   aws_secret_access_key=_plat_secret,
                                                   region_name=_plat_region)
                            _assume_kwargs = {"RoleArn": _wa_role_arn,
                                              "RoleSessionName": "spot-rebalancer-terminate"}
                            if _wa_ext_id:
                                _assume_kwargs["ExternalId"] = _wa_ext_id
                            _assumed_wa = _sts_wa.assume_role(**_assume_kwargs)
                            _cwa = _assumed_wa["Credentials"]
                            _wa_creds = {
                                "aws_access_key_id":     _cwa["AccessKeyId"],
                                "aws_secret_access_key": _cwa["SecretAccessKey"],
                                "aws_session_token":     _cwa["SessionToken"],
                            }
                        elif _plat_key and _plat_secret:
                            # No role ARN — use platform credentials directly
                            _wa_creds = {
                                "aws_access_key_id":     _plat_key,
                                "aws_secret_access_key": _plat_secret,
                            }

                        _terminated = False
                        _term_region = _wa_region

                        # Try 1: ASG terminate with ShouldDecrementDesiredCapacity=True.
                        # When ASG desired == min (e.g. last node), AWS rejects the decrement.
                        # Fix: lower min_size to 0 first so the decrement can proceed.
                        # This prevents the ASG from auto-relaunching an OD replacement after
                        # we resume its Launch process (cluster growth bug).
                        try:
                            _asg_wa = _b3wa.client("autoscaling",
                                                   region_name=_term_region, **_wa_creds)
                            _stored_asg_for_term = _wa_meta.get('asg_name_used')
                            _asg_desired_start = int(_wa_meta.get('asg_desired_at_start', 2))
                            _asg_min_start = int(_wa_meta.get('asg_min_at_start', 1))
                            if _stored_asg_for_term and _asg_desired_start <= _asg_min_start:
                                # Desired would hit min after decrement — lower min temporarily
                                try:
                                    _asg_wa.update_auto_scaling_group(
                                        AutoScalingGroupName=_stored_asg_for_term,
                                        MinSize=0,
                                    )
                                    logger.info(
                                        f"[auto_rebalancer] Lowered ASG '{_stored_asg_for_term}' "
                                        f"min_size to 0 before last-node terminate (action {_wa.id})"
                                    )
                                except Exception as _min_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Could not lower ASG min_size: {_min_err}"
                                    )
                            _asg_wa.terminate_instance_in_auto_scaling_group(
                                InstanceId=_wa_instance_id,
                                ShouldDecrementDesiredCapacity=True
                            )
                            _terminated = True
                            logger.info(
                                f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                f"via ASG (action {_wa.id} post-drain)"
                            )
                        except Exception as _asg_err:
                            logger.warning(
                                f"[auto_rebalancer] ASG terminate failed for {_wa_instance_id}: "
                                f"{_asg_err} — trying direct EC2 terminate"
                            )

                        # Try 2: Direct EC2 terminate
                        if not _terminated:
                            try:
                                _ec2_wa = _b3wa.client("ec2",
                                                       region_name=_term_region, **_wa_creds)
                                _ec2_wa.terminate_instances(InstanceIds=[_wa_instance_id])
                                _terminated = True
                                logger.info(
                                    f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                    f"via direct EC2 API (action {_wa.id} post-drain)"
                                )
                            except Exception as _ec2_err:
                                logger.warning(
                                    f"[auto_rebalancer] Direct EC2 terminate also failed for "
                                    f"{_wa_instance_id}: {_ec2_err}"
                                )

                        if _terminated:
                            _wa_meta['step_5_old_node_terminated'] = datetime.utcnow().isoformat()
                        else:
                            _wa_meta['ec2_terminate_failed'] = True
                            logger.error(
                                f"[auto_rebalancer] CRITICAL: Both EC2 terminate methods failed for "
                                f"{_wa_instance_id} — instance still running on AWS!"
                            )
                    except Exception as _term_err:
                        _terminated = False
                        _wa_meta['ec2_terminate_failed'] = True
                        logger.error(
                            f"[auto_rebalancer] Backend EC2 terminate block failed for "
                            f"{_wa_instance_id}: {_term_err} — instance still running!"
                        )

                    # ── POST-TERMINATE: Resume ASG processes ──────────────────
                    # If we suspended ASG processes during Phase 1 pre-step,
                    # resume them now that the swap is complete.
                    _stored_asg_name = _wa_meta.get('asg_name_used')
                    if _stored_asg_name:
                        try:
                            from backend.utils.aws.asg import (
                                get_assumed_credentials as _gac_resume,
                                resume_asg_processes as _rap_resume,
                            )
                            _wa_cluster_resume = db.query(Cluster).filter(
                                Cluster.id == _wa.cluster_id
                            ).first()
                            if _wa_cluster_resume:
                                _resume_creds = _gac_resume(_wa_cluster_resume, db)
                                _resume_region = (_wa_cluster_resume.region or "ap-south-1")
                                _rap_resume(_stored_asg_name, _resume_region, _resume_creds)
                                logger.info(
                                    f"[auto_rebalancer] Resumed ASG '{_stored_asg_name}' "
                                    f"processes after rebalance completion (action {_wa.id})"
                                )
                        except Exception as _resume_err:
                            logger.warning(
                                f"[auto_rebalancer] Failed to resume ASG processes for "
                                f"'{_stored_asg_name}': {_resume_err}"
                            )


                # ── STATUS DECISION: fail if EC2 terminate failed ────────────────
                _ec2_terminate_failed = _wa_meta.get('ec2_terminate_failed', False)
                if _failed > 0:
                    _wa.status = 'failed'
                elif _ec2_terminate_failed and _wa_instance_id:
                    _wa.status = 'failed'
                    _wa.error_message = (
                        "Agent K8s actions succeeded but EC2 terminate failed — "
                        f"instance {_wa_instance_id} may still be running on AWS"
                    )
                    # Fix 3: drain completed but old OD couldn't die — the replacement
                    # spot instance is now running but receiving no workloads (drain
                    # evacuated the old node). Terminate it to avoid orphan billing.
                    # Note: K8s node object already deleted — uncordon is not possible.
                    _do_rollback_terminate_orphan_spot(_wa, _wa_meta, db)
                else:
                    _wa.status = 'completed'
                _wa.completed_at = datetime.utcnow()
                _wa.duration_seconds = (
                    int((_wa.completed_at - _wa.started_at).total_seconds())
                    if _wa.started_at else 0
                )
                if _failed > 0:
                    _wa_meta['current_step'] = 'failed'
                    # Issue 8b fix: always set step_6 timestamp so UI timeline shows final marker
                    # even for failed actions (prevents incomplete/empty timeline dots)
                    _wa_meta['step_6_optimization_complete'] = datetime.utcnow().isoformat()
                    _wa.error_message = f"{_failed} agent action(s) failed"
                    # Clear per-instance cooldown on failure so the rebalancer can retry.
                    # The cooldown is set at queue time (to prevent in-flight re-targeting),
                    # but must be cleared if the sequence ultimately fails.
                    _wa_inst_id_clear = _wa_meta.get("instance_id", "")
                    if _wa_inst_id_clear and _redis:
                        try:
                            _redis.delete(f"spot:rebalanced:instance:{_wa_inst_id_clear}")
                            logger.info(
                                f"[auto_rebalancer] Cleared cooldown for {_wa_inst_id_clear} "
                                f"(action {_wa.id} failed — allowing retry)"
                            )
                        except Exception:
                            pass
                else:
                    _wa_meta['current_step'] = 'optimization_complete'
                    _wa_meta['step_6_optimization_complete'] = datetime.utcnow().isoformat()

                    # ── POST-SUCCESS: Remove do-not-disrupt from replacement node ──
                    # The replacement node is now the primary; it should participate
                    # in Karpenter consolidation normally going forward.
                    # Issue 3 fix: read from metadata (set when spot joined) instead of
                    # _newest_spot variable which is unreliable across loop iterations.
                    _replacement_node_name = (
                        _wa_meta.get('replacement_node_name') or
                        _wa_meta.get('replacement_spot_node_name')
                    )
                    if _replacement_node_name:
                        try:
                            from backend.models.agent_action import AgentAction as _AA_DP, AgentActionType as _AAT_DP, AgentActionStatus as _AAS_DP
                            _kp_deprotect = _AA_DP(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT_DP.LABEL_NODE,
                                status=_AAS_DP.PENDING,
                                payload={
                                    "node_name": _replacement_node_name,
                                    "labels": {},
                                    "annotations": {"karpenter.sh/do-not-disrupt": "true"},
                                    "remove": True,
                                },
                                action_metadata={"rebalancing_action_id": str(_wa.id),
                                                 "purpose": "release_replacement_node"},
                            )
                            db.add(_kp_deprotect)
                            db.flush()
                        except Exception as _deann_err:
                            logger.warning(
                                f"[auto_rebalancer] Failed to queue do-not-disrupt removal: {_deann_err}"
                            )

                    # ── POST-SUCCESS: Trigger standby node launch ──────────────
                    # If cluster has maintain_standby enabled, launch a new standby
                    try:
                        from backend.models.cluster import ClusterOptimizationSettings
                        _settings = db.query(ClusterOptimizationSettings).filter(
                            ClusterOptimizationSettings.cluster_id == _wa.cluster_id
                        ).first()
                        # Read maintain_standby from the dedicated column (not the JSON blob)
                        if _settings and getattr(_settings, "maintain_standby", False):
                            from backend.workers.tasks.standby import launch_standby_node
                            launch_standby_node.delay(_wa.cluster_id)
                            logger.info(
                                f"[auto_rebalancer] Triggered standby launch for "
                                f"cluster {_wa.cluster_id} after successful rebalance"
                            )
                    except Exception as _standby_err:
                        logger.warning(
                            f"[auto_rebalancer] Standby launch trigger failed: {_standby_err}"
                        )

                    # ── POST-SUCCESS: Recalculate realized savings immediately ──
                    try:
                        from backend.workers.tasks.savings_calculator import calculate_real_savings
                        calculate_real_savings.delay()
                        logger.info(
                            f"[auto_rebalancer] Triggered savings recalculation after "
                            f"completed rebalance action {_wa.id}"
                        )
                    except Exception as _savings_err:
                        logger.warning(
                            f"[auto_rebalancer] Savings recalculation trigger failed: {_savings_err}"
                        )

                _wa.action_metadata = _wa_meta
                logger.info(
                    f"[auto_rebalancer] Action {_wa.id} resolved to {_wa.status} "
                    f"(all AgentActions done, steps: {list(_wa_meta.keys())})"
                )

                # ── POST-FAILURE: Report to Decision Engine ────────────────
                if _wa.status == 'failed':
                    try:
                        from backend.services.decision_engine_service import DecisionEngineService
                        from backend.core.redis_client import get_redis_client as _grc_de
                        _de_svc = DecisionEngineService(db, _grc_de())
                        _target_type = _wa_meta.get("target_instance_type", "")
                        _target_az = _wa_meta.get("target_az", "")
                        if _target_type and _target_az:
                            _de_svc.report_launch_failure(
                                cluster_id=_wa.cluster_id,
                                pool_key=f"{_target_type}:{_target_az}",
                                reason="rebalance_failure",
                            )
                            logger.info(
                                f"[auto_rebalancer] Reported launch failure "
                                f"{_target_type}:{_target_az} to DE"
                            )
                    except Exception as _de_err:
                        logger.warning(
                            f"[auto_rebalancer] DE failure report failed: {_de_err}"
                        )

                # Acquire stabilization lock now that the drain+terminate cycle is truly done
                try:
                    from backend.services.cooldown_controller import CooldownController
                    from backend.core.redis_client import get_redis_client as _grc0
                    CooldownController(_grc0()).acquire_stabilization_lock(
                        _wa.cluster_id, reason="auto_rebalancer_complete"
                    )
                except Exception:
                    pass
            except Exception as _wa_err:
                logger.warning(f"[auto_rebalancer] Error resolving waiting_agent action {_wa.id}: {_wa_err}")
        db.commit()

        # Step 1: Check clusters with auto-rebalancing enabled and create actions for on-demand instances
        from backend.models.cluster import ClusterOptimizationSettings, StatelessRuntimeRules

        # Find clusters with unified auto-rebalance enabled
        active_settings = db.query(ClusterOptimizationSettings).filter(
            ClusterOptimizationSettings.auto_rebalance_enabled == True
        ).all()
        
        cluster_ids = [s.cluster_id for s in active_settings]
        auto_rebalance_clusters = db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).all()

        for cluster in auto_rebalance_clusters:
            # ── STEP 0: Sync real AWS instance state before any decisions ────
            # This ensures DB reflects actual AWS lifecycle, not assumed state.
            try:
                _sync_instance_state_from_aws(db, cluster)
            except Exception as _sync_err:
                logger.warning(f"[auto_rebalancer] AWS sync failed for {cluster.name}: {_sync_err}")

            # ── KARPENTER NODEPOOL REFRESH ────────────────────────────────────
            # When Karpenter is installed, keep its NodePool updated with ML-ranked
            # spot pools every 30 min. Then fall through to cordon/drain/terminate
            # so managed-node-group (ASG) on-demand nodes are actually replaced.
            # The agent's TERMINATE_NODE uses ShouldDecrementDesiredCapacity=True so
            # the ASG won't relaunch a replacement — Karpenter provisions spot instead.
            _karpenter_mode = getattr(cluster, 'karpenter_mode', None)
            _karpenter_active = _karpenter_mode is not None  # any mode (AUTO or DRY_RUN)

            # Also check Redis heartbeat written by agent (set when Karpenter pods detected)
            try:
                _k_key = f"spot:karpenter:installed:{cluster.id}"
                if not _karpenter_active and _redis and _redis.exists(_k_key):
                    _karpenter_active = True
            except Exception:
                pass

            if _karpenter_active:
                # Update NodePool with current ML-ranked spot pools (30-min cooldown).
                # Use the backend's KarpenterService directly (requires no in-cluster agent)
                # so this works even when there are no running nodes.
                _nodepool_cooldown_key = f"spot:karpenter:nodepool_updated:{cluster.id}"
                try:
                    if _redis and not _redis.exists(_nodepool_cooldown_key):
                        try:
                            from backend.services.karpenter_service import KarpenterService
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            from backend.models.instance import Instance as _Inst
                            _od_inst = db.query(_Inst).filter(
                                _Inst.cluster_id == cluster.id,
                                _Inst.lifecycle == InstanceLifecycle.ON_DEMAND
                            ).first()
                            _src_type_np = _od_inst.instance_type if _od_inst else "t3.medium"
                            _specs_np = _INSTANCE_VCPU_MEM.get(_src_type_np, (2, 8))
                            _ranked_np = PoolRankingService(db, _redis).rank_pools_for_size(
                                vcpu=_specs_np[0], memory_gb=float(_specs_np[1]),
                                region=cluster.region or "ap-south-1", limit=10
                            )
                            if _ranked_np:
                                _top_pools = [
                                    {"instance_type": p.pool.instance_type,
                                     "az": p.pool.az,
                                     "ml_score": float(p.ml_score)}
                                    for p in _ranked_np
                                ]
                                _ksvc = KarpenterService(db, _redis)
                                _sync_result = _ksvc.sync_ml_rankings_to_nodepool(
                                    cluster_id=cluster.id,
                                    top_pools=_top_pools,
                                    nodepool_name="default"
                                )
                                if _sync_result.get("status") == "success":
                                    if _redis:
                                        _redis.setex(_nodepool_cooldown_key, 1800, "1")
                                    logger.info(
                                        f"[auto_rebalancer] Karpenter cluster {cluster.name}: "
                                        f"NodePool updated with {len(_top_pools)} ML-ranked pools "
                                        f"(direct backend call — no agent required)"
                                    )
                        except Exception as _ksvc_err:
                            logger.warning(
                                f"[auto_rebalancer] NodePool direct sync failed for "
                                f"{cluster.name}: {_ksvc_err}"
                            )
                except Exception as _kp_err:
                    logger.warning(
                        f"[auto_rebalancer] NodePool ML update failed for Karpenter "
                        f"cluster {cluster.name}: {_kp_err}"
                    )
                # NOTE: Do NOT continue here. Fall through to the cordon/drain/terminate
                # logic below so managed-node-group on-demand nodes are actually replaced.

            # ── SAFETY GATE: OptimizerCoordinator phase (RC-5) ──────────────
            # Don't create new rebalancing actions while right-sizing is mid-execution
            try:
                from backend.models.optimizer_state import OptimizerState
                _opt = db.query(OptimizerState).filter(
                    OptimizerState.cluster_id == cluster.id
                ).first()
                if _opt and _opt.current_phase in ("RIGHTSIZING_EVALUATION", "COMBINED_EXECUTION"):
                    logger.info(
                        f"[auto_rebalancer] Skipping cluster {cluster.name}: "
                        f"optimizer in phase {_opt.current_phase} — would corrupt combined EV calculation"
                    )
                    continue
            except Exception:
                pass  # OptimizerState table may not exist; proceed safely

            # Enforce stateless runtime limits (max rebalances per 24h)
            stateless_rules = db.query(StatelessRuntimeRules).filter(StatelessRuntimeRules.cluster_id == cluster.id).first()
            max_rebalances = stateless_rules.max_rebalances_per_24h if stateless_rules else 5
            
            # Count only COMPLETED actions toward daily limit (deferred/failed don't count)
            recent_rebalances = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.trigger == 'auto_rebalance',
                RebalancingAction.status == 'completed',
                RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24)
            ).count()

            if recent_rebalances >= max_rebalances:
                logger.info(f"Skipping auto-rebalance for cluster {cluster.name}: hit daily limit of {max_rebalances}")
                continue

            # ── ONE-AT-A-TIME GUARDRAIL ──────────────────────────────────────
            # Check if an AgentAction (cordon/drain/patch) is still in flight
            # for this cluster. If so, skip until it completes.
            # Auto-expire stale PENDING/PICKED_UP actions (> 15 min) — these are orphaned by
            # agent restarts and would block the rebalancer indefinitely otherwise.
            # PENDING actions that are >15 min old were never picked up and are effectively dead.
            from backend.models.agent_action import AgentAction, AgentActionStatus
            _expire_cutoff = datetime.utcnow() - timedelta(minutes=15)
            stale_count = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                AgentAction.created_at < _expire_cutoff,
            ).update({"status": AgentActionStatus.EXPIRED}, synchronize_session=False)
            if stale_count:
                db.flush()
                logger.warning(
                    f"[auto_rebalancer] Expired {stale_count} stale PENDING/PICKED_UP AgentAction(s) "
                    f"for cluster {cluster.name} (>15 min old — agent not processing)"
                )
            active_agent_actions = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP])
            ).count()
            if active_agent_actions > 0:
                logger.info(
                    f"[auto_rebalancer] Skipping cluster {cluster.name}: "
                    f"{active_agent_actions} AgentAction(s) still in-flight — waiting for completion"
                )
                continue

            # ── PROACTIVE WARM STANDBY ────────────────────────────────────────
            # If maintain_standby=True and no standby node exists, launch one now.
            # This ensures a pre-warmed node is always available for fast failover.
            try:
                _sb_settings = db.query(ClusterOptimizationSettings).filter(
                    ClusterOptimizationSettings.cluster_id == cluster.id
                ).first()
                if _sb_settings and getattr(_sb_settings, "maintain_standby", False):
                    from backend.services.substitute_manager import SubstituteManager
                    _sb_mgr = SubstituteManager(db, _redis)
                    _sb_status = _sb_mgr.get_substitute_status(cluster.id)
                    _sb_active = (
                        _sb_status.get("is_warm_spare") or
                        _sb_status.get("state") in ("PREWARMING", "ACTIVE")
                    ) if _sb_status else False
                    if not _sb_active:
                        from backend.workers.tasks.standby import launch_standby_node
                        launch_standby_node.delay(cluster.id)
                        logger.info(
                            f"[auto_rebalancer] Proactive standby launch triggered for "
                            f"cluster {cluster.name} (maintain_standby=True, no standby found)"
                        )
            except Exception as _sb_err:
                logger.warning(f"[auto_rebalancer] Proactive standby check failed for {cluster.name}: {_sb_err}")

            # ── LAST-NODE SAFETY GUARD ────────────────────────────────────────
            # Never drain the very last running node — pods would have nowhere to go.
            # Correct logic: check TOTAL running nodes (OD + spot), not just OD count.
            # Example: 1 OD + 1 spot = 2 total → safe to drain the OD (spot absorbs pods).
            # Example: 1 OD + 0 spot = 1 total → unsafe, pods would have nowhere to go.
            _total_nodes = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running',
            ).count()
            _od_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',
            ).count()
            if _total_nodes <= 1:
                if _karpenter_active:
                    # Karpenter is present — update NodePool via direct backend call
                    # (no in-cluster agent required) to signal spot provisioning.
                    # Do NOT cordon/drain yet; wait for spot node to appear.
                    _provision_key = f"spot:karpenter:provision_requested:{cluster.id}"
                    if _redis and not _redis.exists(_provision_key):
                        try:
                            from backend.services.karpenter_service import KarpenterService
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            _any_od = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                            ).first()
                            _src_type = _any_od.instance_type if _any_od else "t3.medium"
                            _specs = _INSTANCE_VCPU_MEM.get(_src_type, (2, 8))
                            _ranked_np = PoolRankingService(db, _redis).rank_pools_for_size(
                                vcpu=_specs[0], memory_gb=float(_specs[1]),
                                region=cluster.region or "ap-south-1", limit=5
                            )
                            _top_np = [
                                {"instance_type": p.pool.instance_type, "az": p.pool.az, "ml_score": float(p.ml_score)}
                                for p in (_ranked_np or [])
                            ]
                            if _top_np:
                                _ksvc2 = KarpenterService(db, _redis)
                                _ksvc2.sync_ml_rankings_to_nodepool(
                                    cluster_id=cluster.id,
                                    top_pools=_top_np,
                                    nodepool_name="default"
                                )
                            if _redis:
                                _redis.setex(_provision_key, 900, "1")  # 15-min cooldown
                            logger.info(
                                f"[auto_rebalancer] Cluster {cluster.name}: only {_od_count} OD node(s) "
                                f"— updated Karpenter NodePool directly (cordon/drain deferred until spot appears)"
                            )
                        except Exception as _np_err:
                            logger.warning(
                                f"[auto_rebalancer] Last-node Karpenter NodePool update failed "
                                f"for {cluster.name}: {_np_err}"
                            )
                else:
                    # Non-Karpenter: launch spot instance directly so the cluster
                    # can grow to 2 nodes and the next cycle can proceed with rebalancing.
                    # Use a 15-min Redis cooldown to avoid duplicate launches.
                    _provision_key = f"spot:direct:provision_requested:{cluster.id}"
                    _launch_failed_key = f"spot:direct:launch_failed:{cluster.id}"
                    if _redis and not _redis.exists(_provision_key) and not _redis.exists(_launch_failed_key):
                        try:
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            _any_od = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                                Instance.state == 'running',
                            ).first()
                            if _any_od:
                                _specs_ln = _INSTANCE_VCPU_MEM.get(_any_od.instance_type, (2, 8))
                                _ranked_ln = PoolRankingService(db, _redis).rank_pools_for_size(
                                    vcpu=_specs_ln[0], memory_gb=float(_specs_ln[1]),
                                    region=cluster.region or "ap-south-1", limit=6
                                )
                                _types_ln = [p.pool.instance_type for p in (_ranked_ln or [])] or [_any_od.instance_type]
                                _new_spot_id, _ln_actual_type, _ln_actual_az = _launch_spot_instance_direct(
                                    db, cluster,
                                    source_instance_id=_any_od.instance_id,
                                    target_instance_types=_types_ln,
                                    target_az=_any_od.az,
                                    region=cluster.region or "ap-south-1",
                                )
                                if _new_spot_id:
                                    if _redis:
                                        _redis.setex(_provision_key, 900, _new_spot_id)
                                    logger.info(
                                        f"[auto_rebalancer] Cluster {cluster.name}: last-node guard "
                                        f"(non-Karpenter) — launched spot {_new_spot_id} "
                                        f"({_ln_actual_type} in {_ln_actual_az}). "
                                        f"Waiting for it to join before draining OD node."
                                    )
                                else:
                                    # Set a 2-min cooldown so we don't retry every 15s
                                    if _redis:
                                        _redis.setex(f"spot:direct:launch_failed:{cluster.id}", 120, "1")
                                    logger.error(
                                        f"[auto_rebalancer] Cluster {cluster.name}: last-node guard "
                                        f"— direct spot launch failed. Retrying in 2 min."
                                    )
                        except Exception as _ln_err:
                            logger.warning(
                                f"[auto_rebalancer] Last-node direct spot launch failed "
                                f"for {cluster.name}: {_ln_err}"
                            )
                    else:
                        _pv = _redis.get(_provision_key) if _redis else None
                        _pending_id = (_pv.decode() if isinstance(_pv, bytes) else (_pv or ""))
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: only {_total_nodes} total / "
                            f"{_od_count} OD node(s) — spot provision already requested "
                            f"({_pending_id or 'cooldown active'}), waiting for it to join"
                        )
                continue

            # ── SPOT RECOVERY: Replace spot-interrupted direct-EC2 nodes ─────
            # Directly-launched spot nodes are NOT in the ASG. When AWS issues a spot
            # interruption, the ASG does not replace them — the cluster silently shrinks.
            # Karpenter handles this automatically for Karpenter clusters. For non-Karpenter
            # direct launch, we detect spots we previously launched that AWS has since
            # terminated (not by our own TERMINATE_NODE action) and relaunch a replacement.
            #
            # Flow:
            #   1. Find all direct-EC2 spots we launched (PATCH_KARPENTER_NODEPOOL with
            #      direct_ec2_launch=True, containing new_ec2_instance_id) in last 7 days.
            #   2. For each: if the instance is terminated AND no matching TERMINATE_NODE
            #      AgentAction exists → AWS terminated it → launch replacement.
            #   3. 1-hour Redis dedup per instance_id to prevent duplicate launches.
            if not _karpenter_active:
                try:
                    from backend.models.agent_action import (
                        AgentAction as _AA_REC,
                        AgentActionType as _AAT_REC,
                        AgentActionStatus as _AAS_REC,
                    )
                    _direct_launches = db.query(_AA_REC).filter(
                        _AA_REC.cluster_id == cluster.id,
                        _AA_REC.action_type == _AAT_REC.PATCH_KARPENTER_NODEPOOL,
                        _AA_REC.payload.contains({"direct_ec2_launch": True}),
                        _AA_REC.created_at >= datetime.utcnow() - timedelta(days=7),
                    ).all()

                    for _dl in _direct_launches:
                        _dl_payload = _dl.payload or {}
                        _launched_spot_id = _dl_payload.get("new_ec2_instance_id")
                        if not _launched_spot_id:
                            continue

                        # Only act if discovery has seen this instance (else it's still launching)
                        _spot_inst = db.query(Instance).filter(
                            Instance.cluster_id == cluster.id,
                            Instance.instance_id == _launched_spot_id,
                        ).first()
                        if not _spot_inst:
                            continue  # Not yet in DB — still launching, check next cycle
                        if _spot_inst.state == 'running':
                            continue  # Still healthy, nothing to do

                        # Instance is terminated — was it us (intentional TERMINATE_NODE)?
                        _our_termination = db.query(_AA_REC).filter(
                            _AA_REC.cluster_id == cluster.id,
                            _AA_REC.action_type == _AAT_REC.TERMINATE_NODE,
                            _AA_REC.payload.contains({"instance_id": _launched_spot_id}),
                            _AA_REC.status == _AAS_REC.COMPLETED,
                        ).first()
                        if _our_termination:
                            continue  # We intentionally replaced it — no recovery needed

                        # AWS terminated it (spot interruption or hardware failure)
                        _recovery_key = f"spot:recovery:{_launched_spot_id}"
                        if _redis and _redis.exists(_recovery_key):
                            continue  # Recovery already in progress, wait for cooldown

                        # Find a running instance to clone user-data / subnet / SG from
                        _ref_od = db.query(Instance).filter(
                            Instance.cluster_id == cluster.id,
                            Instance.state == 'running',
                        ).first()
                        if not _ref_od:
                            logger.warning(
                                f"[auto_rebalancer] Spot recovery: no running instance to "
                                f"clone config from for cluster {cluster.name} — skipping"
                            )
                            continue

                        logger.info(
                            f"[auto_rebalancer] Spot recovery: {_launched_spot_id} was terminated "
                            f"by AWS (not by us) — relaunching replacement for {cluster.name}"
                        )
                        from backend.services.pool_ranking_service import PoolRankingService
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                        _rec_type = _spot_inst.instance_type or "t3.medium"
                        _rec_specs = _INSTANCE_VCPU_MEM.get(_rec_type, (2, 8))
                        _ranked_rec = PoolRankingService(db, _redis).rank_pools_for_size(
                            vcpu=_rec_specs[0], memory_gb=float(_rec_specs[1]),
                            region=cluster.region or "ap-south-1", limit=6
                        )
                        _types_rec = [p.pool.instance_type for p in (_ranked_rec or [])] or [_rec_type]
                        _new_spot_id, _rec_actual_type, _rec_actual_az = _launch_spot_instance_direct(
                            db, cluster,
                            source_instance_id=_ref_od.instance_id,
                            target_instance_types=_types_rec,
                            target_az=_spot_inst.az or "",
                            region=cluster.region or "ap-south-1",
                        )
                        if _new_spot_id:
                            if _redis:
                                _redis.setex(_recovery_key, 3600, _new_spot_id)  # 1h dedup
                            logger.info(
                                f"[auto_rebalancer] Spot recovery: launched {_new_spot_id} "
                                f"({_rec_actual_type} in {_rec_actual_az}) "
                                f"to replace interrupted spot {_launched_spot_id} "
                                f"in cluster {cluster.name}"
                            )
                        else:
                            if _redis:
                                _redis.setex(_recovery_key, 300, "failed")  # retry in 5 min
                            logger.warning(
                                f"[auto_rebalancer] Spot recovery: relaunch failed for "
                                f"{_launched_spot_id} — will retry in 5 min"
                            )
                except Exception as _rec_err:
                    logger.warning(
                        f"[auto_rebalancer] Spot recovery check failed for {cluster.name}: {_rec_err}"
                    )

            # ── KARPENTER PROVISIONING COOLDOWN ──────────────────────────────
            # After draining a node, wait 20 min AND check if Karpenter provisioned
            # a spot node. Only proceed if either a spot node exists OR 20 min elapsed.
            # This prevents cascade-draining all nodes before Karpenter provisions spot.
            last_completed_action = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'completed',
                RebalancingAction.trigger == 'auto_rebalance',
                RebalancingAction.completed_at.isnot(None),
            ).order_by(RebalancingAction.completed_at.desc()).first()
            if last_completed_action and last_completed_action.completed_at:
                elapsed = (datetime.utcnow() - last_completed_action.completed_at).total_seconds()
                _COOLDOWN = 600  # 10-minute strict cooldown between rebalancing actions
                if elapsed < _COOLDOWN:
                    # Strict cooldown: always wait, no exceptions. Spot provisioning now
                    # happens in Phase 1 (before drain), so no need for 20-min Karpenter wait.
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name}: strict {_COOLDOWN}s cooldown "
                        f"({int(_COOLDOWN - elapsed)}s remaining)"
                    )
                    continue

            # Re-queue only the OLDEST deferred action (1 at a time per cluster)
            oldest_deferred = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'deferred'
            ).order_by(RebalancingAction.started_at).first()
            if oldest_deferred:
                oldest_deferred.status = 'in_progress'
                oldest_deferred.started_at = datetime.utcnow()
                logger.info(f"Re-queuing deferred action {oldest_deferred.id} for cluster {cluster.name}")
                # Don't create new actions this cycle — retry the deferred one first
                continue

            # Find on-demand instances that should be migrated to spot
            # IMPORTANT: state='running' filter prevents terminated OD instances
            # (instances already replaced in a previous cycle whose DB record hasn't
            # been cleaned up yet) from being retargeted — which caused an infinite loop
            # where the same "dead" OD node was queued for rebalancing over and over.
            on_demand_instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',   # Only target running OD nodes
            ).all()

            # ── REDIS FALLBACK: seed instances from agent telemetry if DB is empty ──
            # This handles the common case where the agent is running and sending
            # pod/node metrics but the instances table hasn't been populated yet
            # (no AWS discovery configured, or discovery hasn't run).
            if not on_demand_instances:
                _seeded = _seed_instances_from_redis(db, cluster)
                if _seeded:
                    logger.info(
                        f"[auto_rebalancer] Seeded {len(_seeded)} instance(s) from Redis "
                        f"for cluster {cluster.name} — proceeding with rebalancing"
                    )
                    on_demand_instances = _seeded
                else:
                    logger.info(
                        f"[auto_rebalancer] No instances in DB or Redis for cluster {cluster.name} "
                        f"— skipping rebalancing this cycle"
                    )
                    continue

            # ── PER-INSTANCE COOLDOWN: skip instances already rebalanced recently ──
            # After a successful rebalancing, a 24h Redis key is set for the instance.
            # This prevents the infinite loop where AWS sync resets lifecycle to ON_DEMAND
            # and the auto-rebalancer keeps re-targeting the same node.
            try:
                from backend.core.redis_client import get_redis_client as _grc_cd
                _redis_cd = _grc_cd()
                filtered_instances = []
                for inst in on_demand_instances:
                    _cd_key = f"spot:rebalanced:instance:{inst.instance_id}"
                    if _redis_cd.exists(_cd_key):
                        logger.debug(
                            f"[auto_rebalancer] Skipping instance {inst.instance_id}: "
                            f"recently rebalanced (24h cooldown active)"
                        )
                    else:
                        filtered_instances.append(inst)
                on_demand_instances = filtered_instances
            except Exception as _cd_err:
                logger.warning(f"[auto_rebalancer] Instance cooldown check failed: {_cd_err}")

            if not on_demand_instances:
                # ── SPOT-TO-SPOT REBALANCING ────────────────────────────────────────
                # All ON_DEMAND nodes are migrated or in cooldown.
                # Now check SPOT nodes for:
                #   1. Diversify violations  — a family exceeds the 40% cap
                #   2. Risk-based migration  — current pool risk > 0.4 AND a
                #      significantly better alternative exists (Δrisk ≥ 0.15)
                # ───────────────────────────────────────────────────────────────────
                _spot_candidates = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state == 'running',
                ).all()

                if not _spot_candidates:
                    logger.info(
                        f"[auto_rebalancer] No ON_DEMAND or SPOT instances for cluster "
                        f"{cluster.name} — skipping cycle"
                    )
                    continue

                # Load opt settings for S2S checks
                _opt_s2s = db.query(ClusterOptimizationSettings).filter(
                    ClusterOptimizationSettings.cluster_id == cluster.id
                ).first()
                _diversify_s2s = getattr(_opt_s2s, 'diversify_pools', False)

                # Family distribution across ALL currently running nodes
                _all_running_s2s = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()
                _fam_counts_s2s: dict = {}
                for _sri in _all_running_s2s:
                    if _sri.instance_type:
                        _f = _sri.instance_type.split('.')[0]
                        _fam_counts_s2s[_f] = _fam_counts_s2s.get(_f, 0) + 1
                _total_running_s2s = max(1, len(_all_running_s2s))

                _s2s_created = False
                for _sp_inst in _spot_candidates:
                    if not _sp_inst.instance_id or not _sp_inst.instance_id.startswith('i-'):
                        continue

                    # Per-instance cooldown
                    try:
                        if _redis_cd.exists(f"spot:rebalanced:instance:{_sp_inst.instance_id}"):
                            continue
                    except Exception:
                        pass

                    # Daily limit and active-action guard
                    if recent_rebalances >= max_rebalances:
                        break
                    _active_s2s = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent'])
                    ).first()
                    if _active_s2s:
                        break

                    _s2s_trigger_reason = None

                    # ── Check 1: Diversify violation ──────────────────────────────
                    if _diversify_s2s and _sp_inst.instance_type:
                        _sp_fam = _sp_inst.instance_type.split('.')[0]
                        _sp_share = _fam_counts_s2s.get(_sp_fam, 0) / _total_running_s2s
                        if _sp_share > 0.40:
                            _s2s_trigger_reason = (
                                f'diversify_pools: {_sp_fam} family at '
                                f'{_sp_share:.0%} (cap 40%)'
                            )
                            logger.info(
                                f"[auto_rebalancer] S2S diversify trigger: "
                                f"{_sp_inst.instance_id} ({_sp_inst.instance_type}) "
                                f"— {_s2s_trigger_reason}"
                            )

                    # ── Check 2: Risk-based migration ─────────────────────────────
                    if not _s2s_trigger_reason and _sp_inst.instance_type:
                        try:
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM2
                            from backend.services.pool_ranking_service import PoolRankingService as _PRS2
                            _sp_specs = _IVM2.get(_sp_inst.instance_type, (2, 8))
                            _sp_ranked = _PRS2(db, _redis).rank_pools_for_size(
                                vcpu=_sp_specs[0], memory_gb=float(_sp_specs[1]),
                                region=cluster.region or 'ap-south-1', limit=10
                            )
                            if _sp_ranked:
                                _cur_risk_s2s = next(
                                    (_rp.risk_score for _rp in _sp_ranked
                                     if _rp.pool.instance_type == _sp_inst.instance_type),
                                    0.7  # high risk if type not in rankings
                                )
                                _best_alt_s2s = next(
                                    (_rp for _rp in _sp_ranked
                                     if _rp.pool.instance_type != _sp_inst.instance_type),
                                    None
                                )
                                if (_best_alt_s2s
                                        and _cur_risk_s2s > 0.4
                                        and (_cur_risk_s2s - _best_alt_s2s.risk_score) >= 0.15):
                                    _s2s_trigger_reason = (
                                        f'risk_improvement: {_sp_inst.instance_type} '
                                        f'risk={_cur_risk_s2s:.2f} → '
                                        f'{_best_alt_s2s.pool.instance_type} '
                                        f'risk={_best_alt_s2s.risk_score:.2f}'
                                    )
                        except Exception as _rck_err:
                            logger.debug(f'[auto_rebalancer] S2S risk check: {_rck_err}')

                    if not _s2s_trigger_reason:
                        continue  # this SPOT node is fine, check the next one

                    # ── Find best target pool (respecting diversify cap) ──────────
                    try:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM3
                        from backend.services.pool_ranking_service import PoolRankingService as _PRS3
                        _sp_specs3 = _IVM3.get(_sp_inst.instance_type, (2, 8))
                        _sp_ranked3 = _PRS3(db, _redis).rank_pools_for_size(
                            vcpu=_sp_specs3[0], memory_gb=float(_sp_specs3[1]),
                            region=cluster.region or 'ap-south-1', limit=10
                        )
                        _best_s2s_pool = None
                        for _rp3 in _sp_ranked3:
                            if _rp3.pool.instance_type == _sp_inst.instance_type:
                                continue  # never re-migrate to same type
                            if _diversify_s2s:
                                _rp3_fam = _rp3.pool.instance_type.split('.')[0]
                                # After this swap: new family gains one node, current loses one
                                _sim_new_fam_cnt = _fam_counts_s2s.get(_rp3_fam, 0) + 1
                                if _sim_new_fam_cnt / _total_running_s2s > 0.40:
                                    continue  # would over-concentrate the new family
                            _best_s2s_pool = _rp3
                            break

                        if not _best_s2s_pool:
                            logger.debug(
                                f'[auto_rebalancer] S2S: no suitable target pool for '
                                f'{_sp_inst.instance_id} after diversify filter — skipping'
                            )
                            continue

                        _s2s_src = f"{_sp_inst.instance_type}:{_sp_inst.az or cluster.region + 'a'}"
                        _s2s_tgt = f"{_best_s2s_pool.pool.instance_type}:{_best_s2s_pool.pool.az}"

                        _s2s_action = RebalancingAction(
                            cluster_id=cluster.id,
                            trigger='auto_rebalance',
                            source_pool=_s2s_src,
                            target_pool=_s2s_tgt,
                            status='in_progress',
                            started_at=datetime.utcnow(),
                            action_metadata={
                                'reason': _s2s_trigger_reason,
                                'initiated_by': 'auto_rebalancer',
                                'instance_id': _sp_inst.instance_id,
                                'spot_to_spot': True,
                                'target_instance_type': _best_s2s_pool.pool.instance_type,
                                'bin_packed': False,
                            }
                        )
                        db.add(_s2s_action)
                        _s2s_created = True
                        logger.info(
                            f'[auto_rebalancer] SPOT→SPOT action created: '
                            f'{_sp_inst.instance_id} ({_s2s_src} → {_s2s_tgt}) '
                            f'reason={_s2s_trigger_reason}'
                        )
                        break
                    except Exception as _s2s_err:
                        logger.error(f'[auto_rebalancer] S2S action creation error: {_s2s_err}')

                if not _s2s_created:
                    logger.debug(
                        f'[auto_rebalancer] No SPOT→SPOT migration needed for '
                        f'cluster {cluster.name} this cycle'
                    )
                continue  # done with this cluster for this cycle

            # ── SPOT INFO ─────────────────────────────────────────────────────────
            _running_spot_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.SPOT,
                Instance.state == 'running',
            ).count()
            logger.debug(
                f"[auto_rebalancer] Cluster {cluster.name}: "
                f"{_running_spot_count} running spot, {len(on_demand_instances)} remaining OD"
            )

            for instance in on_demand_instances:
                # Skip placeholder instances (daemon-set auto-created with ip- hostname as ID).
                # They don't have real EC2 IDs and can't be used for spot launch.
                if not instance.instance_id or not instance.instance_id.startswith('i-'):
                    logger.debug(
                        f"[auto_rebalancer] Skipping placeholder instance {instance.instance_id} "
                        f"(not a real EC2 ID) for cluster {cluster.name}"
                    )
                    continue

                # ── LIVE AWS LIFECYCLE VERIFICATION ─────────────────────────────
                # Before targeting any instance, confirm from AWS that it really IS
                # on-demand. Karpenter-provisioned spot nodes briefly appear as ON_DEMAND
                # in the DB due to a discovery race condition (AWS sometimes omits
                # InstanceLifecycle in certain describe-instances calls).
                try:
                    from backend.utils.aws.asg import get_assumed_credentials as _get_creds_lv
                    _lv_creds = _get_creds_lv(cluster)
                    if _lv_creds:
                        import boto3 as _boto3_lv
                        _ec2_lv = _boto3_lv.client(
                            'ec2',
                            region_name=cluster.region or 'ap-south-1',
                            aws_access_key_id=_lv_creds.get('AccessKeyId') or _lv_creds.get('access_key'),
                            aws_secret_access_key=_lv_creds.get('SecretAccessKey') or _lv_creds.get('secret_key'),
                            aws_session_token=_lv_creds.get('SessionToken') or _lv_creds.get('session_token'),
                        )
                        _resp_lv = _ec2_lv.describe_instances(InstanceIds=[instance.instance_id])
                        _aws_inst_lv = None
                        for _r in _resp_lv.get('Reservations', []):
                            for _i in _r.get('Instances', []):
                                if _i.get('InstanceId') == instance.instance_id:
                                    _aws_inst_lv = _i
                                    break
                        if _aws_inst_lv:
                            _aws_lc = _aws_inst_lv.get('InstanceLifecycle', 'on-demand')
                            if _aws_lc == 'spot':
                                # AWS says SPOT — correct the DB and skip this instance
                                instance.lifecycle = InstanceLifecycle.SPOT
                                db.commit()
                                _cd_key_lv = f"spot:rebalanced:instance:{instance.instance_id}"
                                try:
                                    get_redis_client().set(_cd_key_lv, '1', ex=86400)
                                except Exception:
                                    pass
                                logger.info(
                                    f"[auto_rebalancer] Live AWS check: {instance.instance_id} is SPOT "
                                    f"(DB was stale ON_DEMAND). Corrected + set 24h cooldown."
                                )
                                continue
                        else:
                            # Instance not found in AWS → already terminated, skip
                            logger.info(
                                f"[auto_rebalancer] Live AWS check: {instance.instance_id} not found "
                                f"in AWS — likely already terminated, skipping."
                            )
                            instance.state = 'terminated'
                            db.commit()
                            continue
                except Exception as _lv_err:
                    logger.debug(f"[auto_rebalancer] Live lifecycle check skipped: {_lv_err}")
                    # Proceed with DB value on error (graceful degradation)

                # Check daily limit
                if (recent_rebalances) >= max_rebalances:
                    logger.info(f"Hit daily limit for cluster {cluster.name}")
                    break

                # Skip if there's already an active rebalancing action for this cluster
                # (includes waiting_agent = queued but agent hasn't finished yet,
                #  and pending_approval = waiting for human to confirm)
                existing_active = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent', 'pending_approval'])
                ).first()
                if existing_active:
                    logger.debug(f"Active action {existing_active.id} already running for cluster {cluster.name} — skipping new creation")
                    break

                # Create new rebalancing action: on-demand → ML-selected spot pool
                source_az = instance.az or f"{cluster.region}a"
                source_pool = f"{instance.instance_type}:{source_az}"

                # ── TOGGLE LOGIC ────────────────────────────────────────────────
                # auto_rebalance only  → ML-rank spot pools at the SAME instance size
                # auto_rebalance+rightsizing → BIN-PACK first (find smaller type based on
                #                              actual CPU/memory usage), then ML-rank for
                #                              the bin-packed size → cheapest + smallest spot
                _opt_settings = db.query(ClusterOptimizationSettings).filter(
                    ClusterOptimizationSettings.cluster_id == cluster.id
                ).first()
                _auto_rightsizing_on = _opt_settings.auto_rightsizing_enabled if _opt_settings else False

                target_instance_type = instance.instance_type  # default: same size
                bin_packed = False
                _reason = 'automatic_spot_migration'

                if _auto_rightsizing_on:
                    # Bin-pack: find smallest instance type that fits actual usage + 30% buffer
                    _cpu_pct = float(instance.cpu_util or 0.0)
                    _mem_pct = float(instance.memory_util or 0.0)
                    if _cpu_pct > 0 and _mem_pct > 0:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                        _cur_specs = _INSTANCE_VCPU_MEM.get(instance.instance_type)
                        if _cur_specs:
                            _BUF = 1.30  # 30% safety headroom above P95 usage
                            _req_vcpu = max(0.25, (_cur_specs[0] * _cpu_pct / 100) * _BUF)
                            _req_mem  = max(0.5,  (_cur_specs[1] * _mem_pct / 100) * _BUF)
                            _PRICES = {
                                "t3.nano":(2,0.5,0.0058),"t3.micro":(2,1.0,0.0116),
                                "t3.small":(2,2.0,0.0232),"t3.medium":(2,4.0,0.0464),
                                "t3.large":(2,8.0,0.0928),"t3.xlarge":(4,16.0,0.1856),
                                "t3.2xlarge":(8,32.0,0.3712),
                                "t3a.micro":(2,1.0,0.0104),"t3a.small":(2,2.0,0.0209),
                                "t3a.medium":(2,4.0,0.0418),"t3a.large":(2,8.0,0.0836),
                                "m5.large":(2,8.0,0.096),"m5.xlarge":(4,16.0,0.192),
                                "m6i.large":(2,8.0,0.096),"m6i.xlarge":(4,16.0,0.192),
                                "c5.large":(2,4.0,0.085),"c5.xlarge":(4,8.0,0.17),
                                "c6i.large":(2,4.0,0.085),"c6g.large":(2,4.0,0.068),
                                "m6g.medium":(1,4.0,0.038),"m6g.large":(2,8.0,0.077),
                                "t4g.micro":(2,1.0,0.0092),"t4g.small":(2,2.0,0.0184),
                                "t4g.medium":(2,4.0,0.0368),"t4g.large":(2,8.0,0.0736),
                            }
                            _cur_hourly = _PRICES.get(instance.instance_type, (None,None,_cur_specs[0]*0.05))[2]
                            # Sort by price ascending; only consider cheaper options
                            _candidates = sorted(
                                [(t,v,m,h) for t,(v,m,h) in _PRICES.items() if h < _cur_hourly],
                                key=lambda x: x[3]
                            )
                            for _t, _v, _m, _h in _candidates:
                                if _v >= _req_vcpu and _m >= _req_mem:
                                    target_instance_type = _t
                                    bin_packed = True
                                    _reason = 'bin_pack_and_spot_migration'
                                    logger.info(
                                        f"[auto_rebalancer] Bin-packed {instance.instance_type} "
                                        f"({_cpu_pct:.0f}%cpu/{_mem_pct:.0f}%mem) → {_t}"
                                    )
                                    break

                # ML-rank: find the best spot pool for the target instance size
                target_pool = source_pool  # fallback
                target_instance_type_final = target_instance_type
                try:
                    from backend.core.redis_client import get_redis_client as _grc
                    from backend.services.pool_ranking_service import PoolRankingService
                    from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                    _specs = _INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
                    _ranked = PoolRankingService(db, _grc()).rank_pools_for_size(
                        vcpu=_specs[0], memory_gb=float(_specs[1]),
                        region=cluster.region or "ap-south-1", limit=10
                    )

                    # ── DIVERSIFY POOLS: 40% family cap + 50% AZ cap ────────────
                    # When diversify_pools=True, skip pools from over-represented
                    # families OR AZs so the cluster doesn't pack all nodes into
                    # one instance type or one availability zone.
                    if _ranked and getattr(_opt_settings, 'diversify_pools', False):
                        from backend.models.instance import Instance as _DivInst
                        _running_insts = db.query(_DivInst).filter(
                            _DivInst.cluster_id == cluster.id,
                            _DivInst.state == 'running',
                        ).all()
                        _total_nodes = len(_running_insts) + 1  # +1 for the incoming node
                        _MAX_FAMILY_SHARE = 0.40  # 40% cap per instance family
                        _MAX_AZ_SHARE = 0.50      # 50% cap per availability zone
                        _family_counts: dict = {}
                        _az_counts: dict = {}
                        for _ri in _running_insts:
                            if _ri.instance_type:
                                _fam = _ri.instance_type.split('.')[0]
                                _family_counts[_fam] = _family_counts.get(_fam, 0) + 1
                            if _ri.az:
                                _az_counts[_ri.az] = _az_counts.get(_ri.az, 0) + 1

                        # Also count instance types being provisioned by in-flight actions
                        # (waiting_agent / in_progress) to prevent duplicate pool launches
                        # while the first replacement node is still joining the cluster.
                        try:
                            _inflight_actions = db.query(RebalancingAction).filter(
                                RebalancingAction.cluster_id == cluster.id,
                                RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent']),
                            ).all()
                            for _ia in _inflight_actions:
                                _ia_type = _ia.target_instance_type
                                _ia_az = _ia.target_az
                                if _ia_type:
                                    _ia_fam = _ia_type.split('.')[0]
                                    _family_counts[_ia_fam] = _family_counts.get(_ia_fam, 0) + 1
                                    _total_nodes += 1
                                if _ia_az:
                                    _az_counts[_ia_az] = _az_counts.get(_ia_az, 0) + 1
                        except Exception as _div_ia_err:
                            logger.debug(f"[auto_rebalancer] In-flight action count failed: {_div_ia_err}")

                        _diversified = []
                        for _rp in _ranked:
                            _rt_name = _rp.pool.instance_type
                            _rp_az   = _rp.pool.az or ""
                            _fam = _rt_name.split('.')[0]
                            _cur_fam_count = _family_counts.get(_fam, 0)
                            _cur_az_count  = _az_counts.get(_rp_az, 0)
                            _fam_ok = (_cur_fam_count + 1) / _total_nodes <= _MAX_FAMILY_SHARE
                            _az_ok  = (_cur_az_count  + 1) / _total_nodes <= _MAX_AZ_SHARE
                            if _fam_ok and _az_ok:
                                _diversified.append(_rp)
                                if len(_diversified) >= 3:
                                    break
                        # If diversification filtered everything out, relax AZ only (not family)
                        if not _diversified:
                            for _rp in _ranked:
                                _rt_name = _rp.pool.instance_type
                                _fam = _rt_name.split('.')[0]
                                _cur_fam_count = _family_counts.get(_fam, 0)
                                if (_cur_fam_count + 1) / _total_nodes <= _MAX_FAMILY_SHARE:
                                    _diversified.append(_rp)
                                    if len(_diversified) >= 3:
                                        break
                        # Last resort: use top-3 as-is
                        _ranked = _diversified if _diversified else _ranked[:3]
                        logger.info(
                            f"[auto_rebalancer] Diversify active: "
                            f"family_counts={_family_counts} az_counts={_az_counts} "
                            f"→ selected {len(_ranked)} pool(s) after family+AZ caps"
                        )
                    else:
                        _ranked = _ranked[:3]

                    if _ranked:
                        _p = _ranked[0].pool
                        target_pool = f"{_p.instance_type}:{_p.az}"
                        target_instance_type_final = _p.instance_type
                except Exception:
                    target_instance_type_final = target_instance_type
                    pass  # Keep fallback to source_pool

                _needs_approval = getattr(_opt_settings, 'manual_approval_required', False)
                _action_status = 'pending_approval' if _needs_approval else 'in_progress'

                rebalancing_action = RebalancingAction(
                    cluster_id=cluster.id,
                    trigger='auto_rebalance',
                    source_pool=source_pool,
                    target_pool=target_pool,
                    status=_action_status,
                    started_at=datetime.utcnow(),
                    action_metadata={
                        'reason': _reason,
                        'initiated_by': 'auto_rebalancer',
                        'instance_id': instance.instance_id,
                        'bin_packed': bin_packed,
                        'target_instance_type': target_instance_type,
                    }
                )

                db.add(rebalancing_action)
                if _needs_approval:
                    logger.info(
                        f"[auto_rebalancer] manual_approval_required=True — created "
                        f"pending_approval action for {instance.instance_id} in cluster "
                        f"{cluster.name}. Approve via POST /api/v1/atharvaai/rebalancing-actions/{{id}}/approve"
                    )
                else:
                    logger.info(f"Created auto-rebalance action for {instance.instance_id} in cluster {cluster.name}")
                break  # Only create 1 action per cluster per cycle

        db.commit()

        # Step 2: Execute 1 in_progress action per cluster (never all at once)
        # Group by cluster_id and pick the oldest in_progress action per cluster.
        from sqlalchemy import func as _sqlfunc
        clusters_with_actions = db.query(RebalancingAction.cluster_id).filter(
            RebalancingAction.status == 'in_progress'
        ).distinct().all()

        executed = 0
        for (cid,) in clusters_with_actions:
            action = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cid,
                RebalancingAction.status == 'in_progress'
            ).order_by(RebalancingAction.started_at).first()
            if action:
                execute_rebalancing_action(db, action)
                executed += 1

        if executed == 0:
            logger.debug("No in_progress rebalancing actions to execute")
        else:
            logger.info(f"Executed {executed} rebalancing action(s) (1 per cluster)")

        logger.info("Auto-rebalancer task completed successfully")

        # ── AUTO-STATEFUL RIGHTSIZING PHASE ──────────────────────────────────────
        # Runs every cycle. When auto_stateful_rightsizing_enabled=True AND
        # StatefulRules.require_approval=False, finds the most over-provisioned
        # ON_DEMAND stateful node and queues CORDON→DRAIN→TERMINATE for OD replacement.
        # Conservative: max 1 node per cluster per cycle, 48h per-node cooldown.
        try:
            from backend.models.cluster import (
                ClusterOptimizationSettings as _COS,
                StatefulRules as _SFRules,
            )
            from backend.models.instance import Instance as _SFInst
            from backend.models.agent_action import AgentAction as _SFAA, AgentActionType as _SFAAType
            from backend.api.karpenter_routes import INSTANCE_SPECS as _SF_SPECS

            _sf_settings = db.query(_COS).filter(
                _COS.auto_stateful_rightsizing_enabled == True
            ).all()

            for _sf_opt in _sf_settings:
                _sf_cid = _sf_opt.cluster_id
                try:
                    # Gate 1: StatefulRules.require_approval must be False
                    _sf_rules = db.query(_SFRules).filter(
                        _SFRules.cluster_id == _sf_cid
                    ).first()
                    if _sf_rules and _sf_rules.require_approval:
                        continue

                    # Gate 2: 48h per-cluster cooldown
                    _sf_cluster_key = f"spot:stateful:resize:cluster:{_sf_cid}"
                    if _redis and _redis.exists(_sf_cluster_key):
                        continue

                    # Find ON_DEMAND instances in this cluster
                    # lifecycle is stored as "on-demand" or "spot" string in DB
                    from backend.models.instance import InstanceLifecycle as _ILC
                    _od_instances = db.query(_SFInst).filter(
                        _SFInst.cluster_id == _sf_cid,
                        _SFInst.lifecycle != _ILC.SPOT,
                        _SFInst.state == "running",
                    ).all()

                    _max_downscale_pct = int(
                        (_sf_rules.max_downscale_percent if _sf_rules else None) or 25
                    )

                    for _sf_inst in _od_instances:
                        _itype = _sf_inst.instance_type
                        _cpu   = float(_sf_inst.cpu_util or 0.0)
                        _mem   = float(_sf_inst.memory_util or 0.0)

                        if _itype not in _SF_SPECS:
                            continue

                        # Per-instance 48h cooldown
                        _sf_inst_key = f"spot:stateful:resize:instance:{_sf_inst.instance_id}"
                        if _redis and _redis.exists(_sf_inst_key):
                            continue

                        # Bin-pack to find recommended type
                        from backend.api.karpenter_routes import _bin_pack_instance as _sf_bpi
                        _rec_type, _resize_savings = _sf_bpi(_itype, _cpu, _mem, buffer_pct=30.0)

                        if _rec_type == _itype or _resize_savings <= 0:
                            continue  # No downsize possible

                        # Validate downscale doesn't exceed max_downscale_pct
                        _cur_hr = _SF_SPECS[_itype][2]
                        _rec_hr = _SF_SPECS.get(_rec_type, (None, None, _cur_hr))[2]
                        _downscale_pct = round((_cur_hr - _rec_hr) / _cur_hr * 100)
                        if _downscale_pct > _max_downscale_pct:
                            logger.debug(
                                f"[auto_rebalancer] Stateful resize skipped: {_sf_inst.instance_id} "
                                f"{_itype}→{_rec_type} would downscale {_downscale_pct}% "
                                f"(max allowed: {_max_downscale_pct}%)"
                            )
                            continue

                        # Queue CORDON → DRAIN (120s) → TERMINATE
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.CORDON_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "stateful_resize": True,
                                "reason": f"auto_stateful_rightsizing: {_itype}→{_rec_type}",
                            },
                        ))
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.DRAIN_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "ignore_daemonsets": True,
                                "grace_period_seconds": 120,
                                "stateful_resize": True,
                            },
                        ))
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.TERMINATE_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "recommended_type": _rec_type,
                                "stateful_resize": True,
                                "decrement_asg": True,
                                "reason": f"auto_stateful_rightsizing: {_itype}→{_rec_type}",
                            },
                        ))

                        # Set 48h cooldowns
                        if _redis:
                            _redis.setex(_sf_inst_key, 172800, "1")
                            _redis.setex(_sf_cluster_key, 172800, "1")

                        db.commit()
                        logger.info(
                            f"[auto_rebalancer] Auto-stateful rightsizing: queued CORDON→DRAIN→TERMINATE "
                            f"for {_sf_inst.instance_id} ({_itype}→{_rec_type}, "
                            f"saves ${_resize_savings}/mo) on cluster {_sf_cid}"
                        )
                        break  # MAX 1 stateful node per cluster per Celery cycle

                except Exception as _sf_err:
                    logger.warning(
                        f"[auto_rebalancer] Auto-stateful rightsizing error for cluster {_sf_cid}: {_sf_err}"
                    )

        except Exception as _sf_outer:
            logger.warning(f"[auto_rebalancer] Auto-stateful rightsizing phase failed: {_sf_outer}")

    except Exception as e:
        logger.error(f"Auto-rebalancer task failed: {e}")
        raise
    finally:
        db.close()
