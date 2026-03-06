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

        # Build map: EC2 instance_id → (lifecycle, instance_type, az) from AWS
        aws_instance_map = {}
        for reservation in response.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                iid = inst['InstanceId']
                # EC2 DescribeInstances: InstanceLifecycle = 'spot' | 'scheduled' | absent (on-demand)
                raw_lc = inst.get('InstanceLifecycle', 'on-demand')
                itype = inst.get('InstanceType', '')
                az = (inst.get('Placement') or {}).get('AvailabilityZone', '')
                aws_instance_map[iid] = {'lifecycle': raw_lc, 'instance_type': itype, 'az': az}
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
            aws_raw_lc = aws_data['lifecycle']
            aws_itype  = aws_data['instance_type']
            aws_az     = aws_data['az']
            real_lifecycle = InstanceLifecycle.SPOT if aws_raw_lc == 'spot' else InstanceLifecycle.ON_DEMAND

            db_inst = db_id_map.get(aws_iid)
            if db_inst is None:
                # ── NEW: create a DB record for every AWS instance we discover ──
                # This is the primary mechanism by which instances enter the system.
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
                        price=0.096,
                        state='running',
                        status='READY',
                        architecture='amd64',
                    )
                    db.add(new_inst)
                    created += 1
                    logger.info(
                        f"[aws_sync] Created instance record {safe_iid} "
                        f"({aws_itype}, {real_lifecycle.value}, {aws_az}) for cluster {cluster.name}"
                    )
                    db_inst = new_inst  # count it for spot/od below
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
                if changed:
                    logger.warning(
                        f"[aws_sync] Corrected {db_inst.instance_id}: "
                        f"lifecycle={real_lifecycle.value}, type={aws_itype}, az={aws_az}"
                    )
                    corrected += 1

            if real_lifecycle == InstanceLifecycle.SPOT:
                spot_count += 1
            else:
                od_count += 1

        # Mark DB instances NOT found in AWS running set as terminated.
        # This cleans up stale records left by terminated/replaced EC2 instances.
        aws_running_truncated = {aws_iid[:20] for aws_iid in aws_instance_map.keys()}
        terminated_count = 0
        for db_inst in db_instances:
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
        _tags = [t for t in _tags if t["Key"] != _cluster_tag]
        _tags.append({"Key": _cluster_tag, "Value": "owned"})
        _tags.append({"Key": "spot-optimizer:launched-by", "Value": "spot-optimizer-direct"})

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
                _run_kwargs = {
                    "ImageId":       _ami_id,
                    "InstanceType":  _itype,
                    "MinCount": 1, "MaxCount": 1,
                    "SubnetId":      _target_subnet,
                    "SecurityGroupIds": _sg_ids,
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
                logger.info(
                    f"[auto_rebalancer] Direct spot launch: {_itype} in {target_az or 'any AZ'} "
                    f"→ EC2 {_new_id} (cluster {cluster.name})"
                )
                return _new_id

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
        return None

    except Exception as _e:
        logger.error(f"[auto_rebalancer] _launch_spot_instance_direct failed: {_e}")
        return None


def execute_rebalancing_action(db: Session, action: RebalancingAction):
        """Execute a single rebalancing action with full cross-system safety gates."""
        from backend.core.redis_client import get_redis_client
        from backend.services.cooldown_controller import CooldownController
        from backend.services.distributed_locks import distributed_lock

        try:
            logger.info(f"Executing rebalancing action {action.id}: {action.cluster_id} ({action.source_pool} → {action.target_pool})")

            cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {action.cluster_id} not found")

            _redis = get_redis_client()
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

                                # Step 1: Suspend ASG processes to prevent interference
                                _asg_suspended = suspend_asg_processes(
                                    _asg_name, _region, _asg_creds
                                )

                                # Step 2: Read current config and reduce desired
                                _asg_info = describe_auto_scaling_group(
                                    _asg_name, _region, _asg_creds
                                )
                                if _asg_info:
                                    _cur_desired = _asg_info["DesiredCapacity"]
                                    _cur_min = _asg_info["MinSize"]
                                    _new_desired = _cur_desired - 1

                                    # Step 3: Handle last OD node — lower MinSize if needed
                                    if _cur_min > _new_desired:
                                        update_asg_min_size(
                                            _asg_name, max(0, _new_desired),
                                            _region, _asg_creds
                                        )
                                        logger.info(
                                            f"[auto_rebalancer] Lowered ASG '{_asg_name}' MinSize "
                                            f"{_cur_min} → {_new_desired} for last-OD swap"
                                        )

                                    # Step 4: Reduce desired capacity
                                    if _new_desired >= 0 and _new_desired < _cur_desired:
                                        import boto3 as _b3_asg
                                        _asg_client = _b3_asg.client(
                                            "autoscaling", region_name=_region, **_asg_creds
                                        )
                                        _asg_client.update_auto_scaling_group(
                                            AutoScalingGroupName=_asg_name,
                                            DesiredCapacity=_new_desired,
                                        )
                                        _asg_reduced = True
                                        logger.info(
                                            f"[auto_rebalancer] Reduced ASG '{_asg_name}' desired "
                                            f"{_cur_desired} → {_new_desired}"
                                        )
                                    else:
                                        logger.info(
                                            f"[auto_rebalancer] ASG '{_asg_name}' already at min "
                                            f"({_cur_min}) — not reducing further"
                                        )
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
                        _new_ec2_id = _launch_spot_instance_direct(
                            db, cluster,
                            source_instance_id=instance_id_for_action,
                            target_instance_types=ml_instance_types,
                            target_az=target_az,
                            region=cluster.region or "ap-south-1",
                        )
                        if not _new_ec2_id:
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

                        # Create a pre-COMPLETED PATCH_NODEPOOL action so the resolution
                        # loop treats Phase 1 as done and waits for the spot node to join.
                        _phase1_payload["direct_ec2_launch"] = True
                        _phase1_payload["new_ec2_instance_id"] = _new_ec2_id
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
            action.pods_migrated = 3
            # Persist ASG state for Phase 2 resume
            _meta_update = dict(action.action_metadata or {})
            if _asg_name_used:
                _meta_update['asg_name_used'] = _asg_name_used
            if _asg_suspended:
                _meta_update['asg_suspended'] = True
            action.action_metadata = _meta_update
            db.commit()

            logger.info(
                f"[auto_rebalancer] Action {action.id} queued 4 agent steps — "
                f"status=waiting_agent until agent completes PATCH_NODEPOOL→CORDON→DRAIN→TERMINATE"
            )

        except Exception as e:
            logger.error(f"Failed to execute rebalancing action {action.id}: {e}")
            action.status = 'failed'
            action.completed_at = datetime.utcnow()
            action.duration_seconds = int((action.completed_at - action.started_at).total_seconds()) if action.started_at else 0
            action.error_message = str(e)
            db.commit()

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
        _keys = _redis.keys(_pattern)
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
                price=0.096,
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

                    # ── Phase 2 creation: spot Ready OR timeout ────────────────
                    if not _phase2_exists:
                        if _wa_karpenter_active and _spot_count == 0 and _spot_wait_elapsed < _SPOT_WAIT_TIMEOUT_S:
                            # Still waiting for spot node — do NOT create drain actions yet
                            _wa_meta['current_step'] = 'waiting_for_spot_node'
                            _wa_meta['spot_wait_elapsed_s'] = int(_spot_wait_elapsed)
                            _wa.action_metadata = _wa_meta
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 1 done, "
                                f"waiting for spot node ({int(_spot_wait_elapsed)}s elapsed, "
                                f"timeout {_SPOT_WAIT_TIMEOUT_S}s)"
                            )
                            db.commit()
                            continue  # Re-check next cycle (outer for _wa loop)

                        if _spot_count > 0:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: spot node Ready! "
                                f"Creating Phase 2 actions (CORDON→DRAIN→TERMINATE)"
                            )
                            _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()
                        elif _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S and _wa_karpenter_active:
                            # Karpenter timeout: Karpenter was supposed to provision but didn't.
                            # Proceed anyway since Karpenter may provision after drain frees capacity.
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: Karpenter spot wait timeout "
                                f"({int(_spot_wait_elapsed)}s). Proceeding with drain (Karpenter should provision after)."
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
                                "Install Karpenter to enable automatic spot provisioning."
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
                            # 5-min timeout: pods may still be stuck but K8s node is already
                            # deleted. UNCORDON_NODE is not a valid AgentActionType, so we
                            # cannot roll back. Log the anomaly and proceed to EC2 terminate.
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

                # Fix 2: Explicit DRAIN failure guard — if DRAIN_NODE failed, DO NOT
                # terminate the EC2 instance.  The node may still be running workloads
                # (drain did not complete), so terminating would destroy live pods.
                # Fail the action cleanly and clear the cooldown so it can be retried.
                if _failed > 0:
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

                        # Try 1: ASG terminate with ShouldDecrementDesiredCapacity=True
                        try:
                            _asg_wa = _b3wa.client("autoscaling",
                                                   region_name=_term_region, **_wa_creds)
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
                else:
                    _wa.status = 'completed'
                _wa.completed_at = datetime.utcnow()
                _wa.duration_seconds = (
                    int((_wa.completed_at - _wa.started_at).total_seconds())
                    if _wa.started_at else 0
                )
                if _failed > 0:
                    _wa_meta['current_step'] = 'failed'
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
                _wa.action_metadata = _wa_meta
                logger.info(
                    f"[auto_rebalancer] Action {_wa.id} resolved to {_wa.status} "
                    f"(all AgentActions done, steps: {list(_wa_meta.keys())})"
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
                                _new_spot_id = _launch_spot_instance_direct(
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
                                        f"(non-Karpenter) — launched spot {_new_spot_id} ({_types_ln[0]}). "
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
                        _pending_id = (_redis.get(_provision_key) or b"").decode() if _redis else ""
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
                        _new_spot_id = _launch_spot_instance_direct(
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
                logger.info(
                    f"[auto_rebalancer] All ON_DEMAND instances in cluster {cluster.name} "
                    f"are in cooldown — skipping this cycle"
                )
                continue

            # ── SPOT SATURATION GUARD ─────────────────────────────────────────────
            # If running spot instances >= remaining running OD instances AND we have
            # at least 1 spot already provisioned, the cluster has grown beyond its
            # original size.  This happens when ASG min_size prevents the last OD node
            # from being safely decremented — ASG relaunches the OD immediately after
            # termination, creating an infinite loop of spot accumulation.
            # Safe resolution: keep the last ASG-protected OD node running and stop.
            # To fully convert (0 OD), set the ASG min_size to 0 first.
            _running_spot_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.SPOT,
                Instance.state == 'running',
            ).count()
            if _running_spot_count > 0 and _running_spot_count >= len(on_demand_instances):
                logger.info(
                    f"[auto_rebalancer] Cluster {cluster.name}: spot saturation guard — "
                    f"{_running_spot_count} running spot node(s) already >= "
                    f"{len(on_demand_instances)} remaining running OD node(s). "
                    f"ASG is likely at min_size; halting rebalancing to prevent infinite "
                    f"OD-relaunch loop. Set ASG min_size=0 to allow full spot conversion."
                )
                continue

            for instance in on_demand_instances:
                # Check daily limit
                if (recent_rebalances) >= max_rebalances:
                    logger.info(f"Hit daily limit for cluster {cluster.name}")
                    break

                # Skip if there's already an active rebalancing action for this cluster
                # (includes waiting_agent = queued but agent hasn't finished yet)
                existing_active = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent'])
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
                try:
                    from backend.core.redis_client import get_redis_client as _grc
                    from backend.services.pool_ranking_service import PoolRankingService
                    from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                    _specs = _INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
                    _ranked = PoolRankingService(db, _grc()).rank_pools_for_size(
                        vcpu=_specs[0], memory_gb=float(_specs[1]),
                        region=cluster.region or "ap-south-1", limit=3
                    )
                    if _ranked:
                        _p = _ranked[0].pool
                        target_pool = f"{_p.instance_type}:{_p.az}"
                except Exception:
                    pass  # Keep fallback to source_pool

                rebalancing_action = RebalancingAction(
                    cluster_id=cluster.id,
                    trigger='auto_rebalance',
                    source_pool=source_pool,
                    target_pool=target_pool,
                    status='in_progress',
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

    except Exception as e:
        logger.error(f"Auto-rebalancer task failed: {e}")
        raise
    finally:
        db.close()
