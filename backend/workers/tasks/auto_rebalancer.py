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
            # Empty result may be transient (EKS tag not yet propagated, API hiccup, wrong tag).
            # Require 3 consecutive empty responses before marking instances terminated.
            # This prevents all nodes from being falsely evicted on a single bad AWS call.
            _empty_streak_key = f"aws_sync:empty_streak:{cluster.id}"
            try:
                from backend.core.redis_client import get_redis_client as _grc_es
                _r_es = _grc_es()
                _empty_streak = int(_r_es.incr(_empty_streak_key) or 0)
                _r_es.expire(_empty_streak_key, 600)  # 10-min TTL (3 × ~3-min cycles)
                logger.warning(
                    f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                    f"(check tag kubernetes.io/cluster/{cluster.name}) "
                    f"— empty streak {_empty_streak}/3"
                )
                if _empty_streak < 3:
                    return  # Transient — don't touch DB yet
                # 3 consecutive empty responses: likely scaled to 0 or tag removed
                _r_es.delete(_empty_streak_key)
            except Exception:
                # Redis unavailable — use conservative single-observation guard:
                # never mass-terminate on a single empty result
                logger.warning(
                    f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                    f"(Redis unavailable for streak guard) — skipping to avoid false termination"
                )
                return
            # Confirmed 3× empty: cluster likely scaled to 0 or misconfigured
            logger.warning(
                f"[aws_sync] Confirmed 3 consecutive empty AWS responses for {cluster.name} "
                f"— marking all DB instances as terminated"
            )
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
                    if (db_inst.lifecycle == InstanceLifecycle.SPOT and
                            real_lifecycle == InstanceLifecycle.ON_DEMAND):
                        # SPOT→OD downgrade: require 3 consecutive AWS observations
                        # to avoid flipping on transient DescribeInstances gaps
                        try:
                            from backend.core.redis_client import get_redis_client as _grc_rc3s
                            _r3s = _grc_rc3s()
                            _sk3s = f"rc3:sync_od_streak:{aws_iid}"
                            _streak3s = int(_r3s.incr(_sk3s) or 0)
                            _r3s.expire(_sk3s, 300)  # 5-min TTL (3 × 15s cycles)
                            if _streak3s >= 3:
                                db_inst.lifecycle = real_lifecycle
                                _r3s.delete(_sk3s)
                                changed = True
                                logger.info(f"[aws_sync] RC3: confirmed SPOT→OD for {aws_iid} after 3 consecutive OD observations")
                            # else: keep SPOT (transient absence)
                        except Exception as _rc3_err:
                            # Redis unavailable — keep current SPOT lifecycle.
                            # Downgrading on a transient Redis error would cause false OD
                            # classification and trigger unnecessary rebalancing.
                            logger.warning(
                                f"[aws_sync] RC3 guard Redis error for {aws_iid}: {_rc3_err} "
                                f"— keeping current lifecycle {db_inst.lifecycle} (no change)"
                            )
                    else:
                        db_inst.lifecycle = real_lifecycle
                        changed = True
                        # Clear any stale RC3 streak when confirmed non-SPOT
                        try:
                            from backend.core.redis_client import get_redis_client as _grc_rc3c
                            _grc_rc3c().delete(f"rc3:sync_od_streak:{aws_iid}")
                        except Exception:
                            pass
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
) -> tuple:
    """
    Launch a spot EC2 instance for non-Karpenter clusters.
    Returns (instance_id, instance_type, az, error_msg). error_msg is None on success.

    Copies AMI, subnet, security groups, IAM instance profile, and cluster tags
    from the source OD instance, then calls run_instances() with spot market options.
    Tries each target_instance_type in order, falling back on InsufficientInstanceCapacity.

    Returns the new EC2 instance_id on success, or None on failure.
    """
    _last_err = None  # tracks the most recent AWS error for caller reporting
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
        try:
            _resp = _ec2.describe_instances(InstanceIds=[source_instance_id])
            _src  = _resp["Reservations"][0]["Instances"][0]
        except _CE as _ce:
            if _ce.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                if not _role_arn:
                    raise ValueError(f"CRITICAL ERROR: Cannot access customer AWS account for cluster {cluster.name}. No 'aws_role_arn' is configured. Please link an AWS account.")
                else:
                    raise ValueError(f"CRITICAL ERROR: Cannot find instance {source_instance_id} using role {_role_arn}. Verify cross-account IAM permissions.")
            raise

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
        # Attempt 1: describe_instance_attribute (requires ec2:DescribeInstanceAttribute IAM perm)
        try:
            _ud_resp = _ec2.describe_instance_attribute(
                InstanceId=source_instance_id, Attribute="userData"
            )
            _user_data_b64 = _ud_resp.get("UserData", {}).get("Value", "")
            if _user_data_b64:
                logger.info(
                    f"[auto_rebalancer] Got user-data via instance attribute for {source_instance_id} "
                    f"({len(_user_data_b64)} chars base64)"
                )
        except Exception as _ud_err:
            logger.warning(
                f"[auto_rebalancer] Could not fetch user-data via DescribeInstanceAttribute "
                f"for {source_instance_id}: {_ud_err} — trying launch template fallback"
            )

        # Attempt 2: get user-data from the source instance's launch template (EKS managed node groups
        # store the bootstrap script in the launch template, not the instance attribute directly).
        # This also handles the case where ec2:DescribeInstanceAttribute is not granted.
        if not _user_data_b64:
            try:
                _lt_info = _src.get("LaunchTemplate", {})
                _lt_id = _lt_info.get("LaunchTemplateId")
                _lt_version = str(_lt_info.get("Version") or "$Default")
                if _lt_id:
                    _lt_resp = _ec2.describe_launch_template_versions(
                        LaunchTemplateId=_lt_id,
                        Versions=[_lt_version],
                    )
                    _lt_versions = _lt_resp.get("LaunchTemplateVersions", [])
                    if _lt_versions:
                        _lt_ud = _lt_versions[0].get("LaunchTemplateData", {}).get("UserData", "")
                        if _lt_ud:
                            _user_data_b64 = _lt_ud
                            logger.info(
                                f"[auto_rebalancer] Got user-data from launch template "
                                f"{_lt_id}:{_lt_version} ({len(_user_data_b64)} chars base64)"
                            )
                        else:
                            logger.warning(
                                f"[auto_rebalancer] Launch template {_lt_id}:{_lt_version} "
                                f"has no user-data"
                            )
                else:
                    logger.warning(
                        f"[auto_rebalancer] Source instance {source_instance_id} has no "
                        f"LaunchTemplate association — cannot get user-data from LT"
                    )
            except Exception as _lt_err:
                logger.warning(
                    f"[auto_rebalancer] Could not fetch user-data from launch template: {_lt_err}"
                )

        # Attempt 3: Get user-data from the EKS managed node group launch template.
        # This is the most reliable source — it is the authoritative bootstrap script
        # for this EKS cluster, independent of which running instance we copied from.
        # REQUIRED when source_instance_id is a direct-launched node (no LT association).
        if not _user_data_b64:
            try:
                import boto3 as _b3_eks3
                _eks3 = _b3_eks3.client("eks", region_name=region, **_creds)
                _eks_cluster_name = (
                    getattr(cluster, 'eks_cluster_name', None)
                    or getattr(cluster, 'name', None)
                    or cluster.name
                )
                _ngs = _eks3.list_nodegroups(clusterName=_eks_cluster_name).get('nodegroups', [])
                for _ng_name in _ngs:
                    _ng = _eks3.describe_nodegroup(
                        clusterName=_eks_cluster_name, nodegroupName=_ng_name
                    )['nodegroup']
                    _ng_lt = _ng.get('launchTemplate', {})
                    _ng_lt_id = _ng_lt.get('id')
                    _ng_lt_ver = str(_ng_lt.get('version') or '$Default')
                    if _ng_lt_id:
                        _lt3 = _ec2.describe_launch_template_versions(
                            LaunchTemplateId=_ng_lt_id, Versions=[_ng_lt_ver]
                        ).get('LaunchTemplateVersions', [])
                        if _lt3:
                            _ud3 = _lt3[0].get('LaunchTemplateData', {}).get('UserData', '')
                            if _ud3:
                                _user_data_b64 = _ud3
                                logger.info(
                                    f"[auto_rebalancer] Got user-data from EKS nodegroup "
                                    f"'{_ng_name}' LT {_ng_lt_id}:{_ng_lt_ver} "
                                    f"({len(_user_data_b64)} chars base64)"
                                )
                                break
                if not _user_data_b64:
                    logger.warning(
                        f"[auto_rebalancer] EKS nodegroup LT user-data: no nodegroup had user-data "
                        f"for cluster '{_eks_cluster_name}'"
                    )
            except Exception as _eks3_err:
                logger.warning(
                    f"[auto_rebalancer] Attempt 3 (EKS nodegroup LT): {_eks3_err}"
                )

        if not _user_data_b64:
            logger.error(
                f"[auto_rebalancer] *** No user-data found for {source_instance_id} ***  "
                f"New spot node will launch WITHOUT the EKS bootstrap script — "
                f"kubelet will NOT start and the node will NOT join the cluster. "
                f"Grant ec2:DescribeInstanceAttribute + ec2:DescribeLaunchTemplateVersions "
                f"to the cross-account IAM role to fix this."
            )

        # Copy existing tags; add/update cluster ownership and platform marker
        _tags = [t for t in _src.get("Tags", []) if not t["Key"].startswith("aws:")]
        _cluster_tag = f"kubernetes.io/cluster/{cluster.name}"
        # Strip all keys we will re-set below to prevent InvalidParameterValue: Duplicate tag key.
        _STRIP_KEYS = {
            _cluster_tag,
            "spot-optimizer:status",
            "spot-optimizer:launched-by",
            "spot-optimizer:template-id",
            "spot-optimizer:termination-mode",
            "spot-optimizer:allowed-architectures",
        }
        _tags = [t for t in _tags if t["Key"] not in _STRIP_KEYS]
        _tags.append({"Key": _cluster_tag, "Value": "owned"})
        _tags.append({"Key": "spot-optimizer:launched-by", "Value": "spot-optimizer-direct"})
        # ── Task 3.9: Additional node labels at launch ────────────────
        _tags.append({"Key": "spot-optimizer:template-id", "Value": source_instance_id[:20]})
        _tags.append({"Key": "spot-optimizer:termination-mode", "Value": "replacement"})
        # allowed-architectures: set based on source instance family (from described EC2 data)
        _ARM_FAMILIES_TAG = {'t4g', 'c6g', 'c7g', 'm6g', 'm7g', 'r6g', 'r7g',
                             'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g'}
        _src_instance_type = _src.get("InstanceType", "")  # from describe_instances response
        _src_fam = _src_instance_type.split('.')[0] if _src_instance_type else ''
        _arch_tag_val = "arm64" if _src_fam in _ARM_FAMILIES_TAG else "x86_64"
        _tags.append({"Key": "spot-optimizer:allowed-architectures", "Value": _arch_tag_val})
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

        # Copy public IP setting from source instance.
        # If source EKS nodes have public IPs (public subnets with MapPublicIpOnLaunch=True),
        # the spot replacement MUST also get a public IP to reach the EKS API server.
        # Without this, kubelet bootstrap fails: node never joins the cluster.
        # Root cause of orphan c5.large (i-0beb31e95ae1af124) not joining EKS cluster.
        _src_has_public_ip = bool(_src.get("PublicIpAddress"))

        # Try each instance type in priority order; skip on capacity errors
        # Task 4.8: configurable cascade limit (default 6)
        _max_attempts = 6
        try:
            from backend.models.cluster import ClusterOptimizationSettings
            _opt_settings = db.query(ClusterOptimizationSettings).filter(
                ClusterOptimizationSettings.cluster_id == cluster.id
            ).first()
            if _opt_settings and _opt_settings.max_instance_type_attempts:
                _max_attempts = _opt_settings.max_instance_type_attempts
        except Exception:
            pass
        # Track which types were tried and why they failed so callers can record
        # the reason a pool was changed from the originally planned type.
        _skipped: dict = {}  # {instance_type: "ErrorCode: message"}
        for _itype in (target_instance_types or ["t3.medium"])[:_max_attempts]:
            try:
                _run_kwargs = {
                    "ImageId":      _ami_id,
                    "InstanceType": _itype,
                    "MinCount": 1, "MaxCount": 1,
                    "NetworkInterfaces": [{
                        "DeviceIndex": 0,
                        "SubnetId": _target_subnet,
                        "Groups": _sg_ids,
                        "AssociatePublicIpAddress": _src_has_public_ip,
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
                    + (f" [skipped: {_skipped}]" if _skipped else "")
                )
                return _new_id, _itype, _actual_az, None, _skipped

            except _CE as _ce:
                _code = _ce.response["Error"]["Code"]
                _msg = _ce.response["Error"].get("Message", str(_ce))
                _last_err = f"{_code}: {_msg}"
                if _code in ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow",
                             "InstanceLimitExceeded", "Unsupported"):
                    _skipped[_itype] = f"{_code}: {_msg}"
                    logger.warning(
                        f"[auto_rebalancer] {_itype} unavailable ({_code}), trying next type"
                    )
                    continue
                raise  # Unexpected error — propagate

        _capacity_err = (
            f"All instance types exhausted ({', '.join(target_instance_types[:3])}) "
            f"in {target_az or 'any AZ'}"
            + (f" — last AWS error: {_last_err}" if _last_err else "")
        )
        logger.error(f"[auto_rebalancer] {_capacity_err} for cluster {cluster.name}")
        return None, None, None, _capacity_err, _skipped

    except Exception as _e:
        _err_str = str(_e)
        logger.error(f"[auto_rebalancer] _launch_spot_instance_direct failed: {_err_str}")
        return None, None, None, _err_str, {}


def execute_rebalancing_action(db: Session, action: RebalancingAction):
        """Execute a single rebalancing action with full cross-system safety gates."""
        from backend.core.redis_client import get_redis_client, key_cluster_cooldown, key_rebalance_lock
        from backend.services.cooldown_controller import CooldownController
        from backend.services.distributed_locks import distributed_lock

        # Track lock state outside try so finally can always release it
        _lock_key_release = None
        _redis_release = None

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
            if _lock_acquired:
                # Store refs so finally block can always release the lock
                _lock_key_release = _lock_key
                _redis_release = _redis
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

            # ── DOUBLE-LAUNCH GUARD ───────────────────────────────────────────
            # If replacement_spot_instance_id is already set in metadata, Phase 1
            # (spot launch) already ran. Transitioning to waiting_agent at line 1241
            # should prevent re-entry, but this explicit guard protects against race
            # conditions where the action is still in_progress when the next cycle runs.
            _existing_replacement = (action.action_metadata or {}).get('replacement_spot_instance_id')
            if _existing_replacement:
                logger.info(
                    f"[auto_rebalancer] Action {action.id}: spot {_existing_replacement} already launched "
                    f"— skipping Phase 1, transitioning to waiting_agent"
                )
                action.status = 'waiting_agent'
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
                            # ── RESPECT DIVERSIFICATION: honour the action's target_instance_type ──
                            # The action was created with a diversification-filtered pool selection
                            # (pool-unique + family-capped). If we re-rank without that filter we
                            # end up launching the ML-top type (e.g. c6i.large) regardless of what
                            # was already running — causing pool duplication and family cap violations.
                            #
                            # Fix A: include both 'running' AND 'pending' instances so that a
                            # pre-registered spot instance (state='pending', launched by a previous
                            # action in the same batch) blocks its pool from being chosen as a
                            # fallback — preventing two c5.large in the same AZ.
                            #
                            # Fix B: apply the same occupancy filter to target_instance_type (the
                            # primary type, set at action-creation time). If the pool became occupied
                            # between creation and execution, we defer rather than duplicate.
                            _occupied_exec = set(
                                (i.instance_type, i.az or '')
                                for i in db.query(Instance).filter(
                                    Instance.cluster_id == action.cluster_id,
                                    Instance.state.in_(['running', 'pending']),
                                    Instance.instance_id.like('i-%'),
                                ).all()
                                if i.instance_type and i.az
                            )
                            # All candidate types (primary + fallbacks), deduplicated, diversified
                            _all_candidate_types = list(dict.fromkeys(
                                [target_instance_type] +
                                [p.pool.instance_type for p in _ranked_ml]
                            ))
                            _diversified_types = [
                                t for t in _all_candidate_types
                                if (t, target_az) not in _occupied_exec
                            ]
                            if _diversified_types:
                                ml_instance_types = _diversified_types[:8]
                            else:
                                # Every candidate pool is already occupied — defer to next cycle
                                # rather than growing the cluster with a duplicate.
                                logger.info(
                                    f"[auto_rebalancer] All candidate pools for "
                                    f"{target_instance_type}:{target_az} occupied — deferring "
                                    f"action {action.id} to next cycle (diversification constraint)"
                                )
                                action.status = 'deferred'
                                action.error_message = (
                                    f"All candidate spot pools for {target_az} are currently occupied "
                                    f"(diversification constraint). Will retry next cycle."
                                )
                                db.commit()
                                return
                            logger.info(
                                f"[auto_rebalancer] Exec ml_instance_types (diversified, "
                                f"pool-filtered): {ml_instance_types[:4]}"
                            )
                    except Exception:
                        pass

                    # ── ARCHITECTURE FILTER ────────────────────────────────────────
                    # _launch_spot_instance_direct() copies the source instance's AMI.
                    # An amd64 AMI cannot boot ARM64 types (c6g, m6g, t4g, etc.)
                    # and vice-versa.  Filter ml_instance_types to the source arch
                    # so we never attempt a cross-arch launch that silently fails
                    # and falls through to a larger/wrong instance type.
                    _ARM64_FAMILIES = {'t4g', 'c6g', 'c7g', 'm6g', 'm7g', 'r6g', 'r7g',
                                       'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g'}
                    _source_family = source_instance_type.split('.')[0] if source_instance_type else ''
                    _source_is_arm = _source_family in _ARM64_FAMILIES
                    _pre_filter_count = len(ml_instance_types)
                    if _source_is_arm:
                        # Source is ARM64 — keep only ARM64 types
                        ml_instance_types = [
                            t for t in ml_instance_types
                            if t.split('.')[0] in _ARM64_FAMILIES
                        ]
                    else:
                        # Source is amd64 — exclude all ARM64 types
                        ml_instance_types = [
                            t for t in ml_instance_types
                            if t.split('.')[0] not in _ARM64_FAMILIES
                        ]
                    if not ml_instance_types:
                        # Architecture filter removed all candidates — use source type
                        ml_instance_types = [source_instance_type or 't3.medium']
                    if len(ml_instance_types) != _pre_filter_count:
                        logger.info(
                            f"[auto_rebalancer] Filtered ml_instance_types by arch "
                            f"({'arm64' if _source_is_arm else 'amd64'}): "
                            f"{_pre_filter_count} → {len(ml_instance_types)} types: "
                            f"{ml_instance_types[:5]}"
                        )

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

                        # ── PRE-LAUNCH ORPHAN DETECTION ────────────────────────────
                        # If a previous rebalancing action for the SAME source instance
                        # failed and its orphan spot wasn't cleaned up (e.g. rollback
                        # ran before discovery synced the DB), terminate it now before
                        # launching a new one.  Prevents unbounded node growth.
                        try:
                            _prev_failed = db.query(RebalancingAction).filter(
                                RebalancingAction.cluster_id == action.cluster_id,
                                RebalancingAction.status == 'failed',
                                RebalancingAction.id != action.id,
                                RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24),
                            ).all()
                            for _pf in _prev_failed:
                                _pf_meta = _pf.action_metadata or {}
                                if _pf_meta.get('instance_id') != instance_id_for_action:
                                    continue  # different source instance
                                _pf_orphan = _pf_meta.get('replacement_spot_instance_id')
                                _pf_rolled = _pf_meta.get('rollback_terminated_spot')
                                if _pf_orphan and _pf_orphan.startswith('i-') and _pf_orphan != _pf_rolled:
                                    # Orphan exists and wasn't terminated by rollback
                                    # Verify it's still running via AWS before terminating
                                    try:
                                        from backend.utils.aws.asg import get_assumed_credentials as _gac_orphan
                                        import boto3 as _b3_orphan
                                        _oc = _gac_orphan(cluster, db)
                                        _oec2 = _b3_orphan.Session(
                                            aws_access_key_id=_oc.get('AccessKeyId'),
                                            aws_secret_access_key=_oc.get('SecretAccessKey'),
                                            aws_session_token=_oc.get('SessionToken'),
                                        ).client('ec2', region_name=cluster.region or 'ap-south-1')
                                        _or = _oec2.describe_instances(InstanceIds=[_pf_orphan])
                                        _o_state = 'terminated'
                                        for _orr in _or.get('Reservations', []):
                                            for _oi in _orr.get('Instances', []):
                                                _o_state = _oi.get('State', {}).get('Name', 'terminated')
                                        if _o_state in ('running', 'pending'):
                                            _oec2.terminate_instances(InstanceIds=[_pf_orphan])
                                            logger.info(
                                                f"[auto_rebalancer] Pre-launch orphan cleanup: "
                                                f"terminated {_pf_orphan} (from failed action {_pf.id}) "
                                                f"before launching new spot for {instance_id_for_action}"
                                            )
                                            # Record cleanup in old action metadata
                                            _pf_meta['rollback_terminated_spot'] = _pf_orphan
                                            _pf.action_metadata = _pf_meta
                                            db.flush()
                                    except Exception as _oe:
                                        # Cannot confirm orphan state — fail the action.
                                        # Launching a new spot without cleaning up a potential orphan
                                        # risks growing the cluster beyond its original size.
                                        logger.error(
                                            f"[auto_rebalancer] Pre-launch orphan cleanup FAILED "
                                            f"for {_pf_orphan}: {_oe} — aborting action to prevent "
                                            f"duplicate instances. Manual cleanup required."
                                        )
                                        action.status = 'failed'
                                        action.error_message = (
                                            f"Pre-launch orphan cleanup failed for {_pf_orphan}: {_oe}. "
                                            f"Manual intervention required before retrying."
                                        )
                                        db.commit()
                                        return
                        except Exception as _pf_err:
                            # Cannot check for orphan instances — fail the action.
                            # Proceeding without this check risks duplicate instances in the cluster.
                            logger.error(
                                f"[auto_rebalancer] Pre-launch orphan detection FAILED: {_pf_err} "
                                f"— aborting action to prevent unbounded cluster growth."
                            )
                            action.status = 'failed'
                            action.error_message = (
                                f"Pre-launch orphan detection failed: {_pf_err}. "
                                f"Cannot safely launch spot instance without confirming no orphans exist."
                            )
                            db.commit()
                            return

                        # Track launch attempt for pool reliability metrics
                        try:
                            from backend.services.pool_ranking_service import report_launch_attempt as _rla
                            for _lt in ml_instance_types[:3]:
                                _rla(f"{_lt}:{target_az}")
                        except Exception:
                            pass

                        _new_ec2_id, _actual_itype, _actual_az, _launch_err, _launch_skipped = _launch_spot_instance_direct(
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

                            action.status = 'failed'
                            action.error_message = _launch_err or (
                                f"Direct spot EC2 launch failed for types {ml_instance_types[:3]}"
                            )
                            db.commit()
                            return

                        # Update target_pool to the ACTUAL launched type (not just ML top pick)
                        _original_target_pool = action.target_pool  # preserve planned pool before overwrite
                        if _actual_itype and _actual_az:
                            action.target_pool = f"{_actual_itype}:{_actual_az}"

                        # Pre-register the new spot instance in DB immediately so that
                        # metrics.py (which doesn't see K8s lifecycle labels for direct-launched
                        # nodes) cannot create it as ON_DEMAND. The RC3 guard then protects
                        # it for the first 90 s until aws_sync confirms.
                        try:
                            _safe_new_id = _new_ec2_id[:20]
                            _exists_new = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.instance_id == _safe_new_id,
                            ).first()
                            if not _exists_new:
                                _pre_inst = Instance(
                                    cluster_id=cluster.id,
                                    instance_id=_safe_new_id,
                                    instance_type=_actual_itype or "unknown",
                                    lifecycle=InstanceLifecycle.SPOT,
                                    az=_actual_az or f"{cluster.region or 'ap-south-1'}a",
                                    price=0.0,
                                    state='pending',
                                    status='PENDING',
                                    architecture='amd64',
                                )
                                db.add(_pre_inst)
                                db.flush()
                                logger.info(
                                    f"[auto_rebalancer] Pre-registered {_safe_new_id} "
                                    f"({_actual_itype}) as SPOT in DB — prevents false OD classification"
                                )
                        except Exception as _pre_reg_err:
                            logger.warning(f"[auto_rebalancer] Pre-register spot instance failed: {_pre_reg_err}")

                        # Create a pre-COMPLETED PATCH_NODEPOOL action so the resolution
                        # loop treats Phase 1 as done and waits for the spot node to join.
                        _phase1_payload["direct_ec2_launch"] = True
                        _phase1_payload["new_ec2_instance_id"] = _new_ec2_id
                        _phase1_payload["actual_instance_type"] = _actual_itype
                        # Store in RebalancingAction metadata: replacement ID, original
                        # planned pool, and reason if pool changed due to capacity issues.
                        _meta_update_p1 = dict(action.action_metadata or {})
                        _meta_update_p1['replacement_spot_instance_id'] = _new_ec2_id
                        _original_itype_p1 = (_original_target_pool or '').split(':')[0]
                        if _actual_itype and _actual_itype != _original_itype_p1:
                            _meta_update_p1['original_target_pool'] = _original_target_pool
                            _skipped_summary = '; '.join(
                                f"{t}: {e}" for t, e in (_launch_skipped or {}).items()
                            )
                            _meta_update_p1['pool_change_reason'] = (
                                f"{_original_itype_p1} → {_actual_itype} "
                                f"(capacity unavailable"
                                + (f": {_skipped_summary}" if _skipped_summary else "")
                                + ")"
                            )
                            # Blacklist each InsufficientInstanceCapacity pool for 6h so
                            # the ML engine avoids re-selecting it this session.
                            if _launch_skipped:
                                try:
                                    from backend.services.blacklist_service import BlacklistService as _BLS
                                    if _redis:
                                        _bls = _BLS(_redis)
                                        _region_bl = cluster.region or "ap-south-1"
                                        for _bl_type, _bl_err_str in _launch_skipped.items():
                                            if "InsufficientInstanceCapacity" in _bl_err_str:
                                                _bls.blacklist_pool(
                                                    instance_type=_bl_type,
                                                    az=target_az or "",
                                                    region=_region_bl,
                                                    reason="InsufficientInstanceCapacity during launch cascade",
                                                    ttl_override_hours=6,
                                                )
                                                logger.info(
                                                    f"[auto_rebalancer] Blacklisted {_bl_type}:{target_az} "
                                                    f"for 6h (InsufficientInstanceCapacity, action {action.id})"
                                                )
                                except Exception as _bl_ex:
                                    logger.warning(f"[auto_rebalancer] Capacity blacklist update failed: {_bl_ex}")
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
        finally:
            # Always release the rebalance lock when execution completes (success, failure, or exception)
            if _lock_key_release and _redis_release:
                try:
                    _redis_release.delete(_lock_key_release)
                except Exception:
                    pass


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

    # Guard: if the cluster already has any running instances in the DB (even ip- placeholders),
    # don't create NEW synthetic instances. Discovery will eventually link ip- records to i- IDs.
    # Seeding is only for clusters with ZERO instance records.
    # Also: if ANY spot instances exist in the cluster (running OR terminated recently),
    # never seed with ON_DEMAND defaults — this would cause false OD detection and
    # trigger unnecessary spot launches, growing the cluster.
    try:
        _existing_count = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
        ).count()
        if _existing_count > 0:
            return []
    except Exception:
        pass

    # Secondary guard: if cluster has ANY spot instances (even recently terminated),
    # don't seed. A cluster with known spot history should not get fake OD seeds.
    try:
        _spot_exists = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
        ).first()
        if _spot_exists:
            logger.debug(
                f"[seed_redis] Cluster {cluster.id} has spot instance history — "
                f"skipping ON_DEMAND seed to prevent false rebalancing"
            )
            return []
    except Exception:
        pass

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

            # Skip if already exists in DB.
            # Do NOT re-add existing ip- placeholder records to the seeded list —
            # they may be stale (spot nodes whose EC2 'i-' ID was later discovered),
            # and targeting them for rebalancing causes launch failures because
            # 'ip-xxx' is not a valid EC2 instance ID.
            existing = db.query(Instance).filter(Instance.instance_id == _short_id).first()
            if existing:
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

        # Resolve the EC2 instance ID to terminate (DB record OR direct from metadata)
        _terminate_id = None
        if _orphan_inst and _orphan_inst.instance_id:
            _terminate_id = _orphan_inst.instance_id
        elif _orphan_id and _orphan_id.startswith('i-'):
            # DB record doesn't exist yet (discovery hasn't synced), but we know
            # the exact instance_id from Phase 1 metadata → terminate directly.
            _terminate_id = _orphan_id
            logger.info(
                f"[rollback] Orphan {_orphan_id} not in DB yet (discovery lag) "
                f"— terminating directly via EC2 API (action {wa.id})"
            )

        if _terminate_id:
            from backend.utils.aws.asg import get_assumed_credentials as _gac_spot
            import boto3 as _b3spot
            _spot_creds = _gac_spot(_rb_cluster, db)
            _spot_ec2 = _b3spot.Session(
                aws_access_key_id=_spot_creds.get('AccessKeyId'),
                aws_secret_access_key=_spot_creds.get('SecretAccessKey'),
                aws_session_token=_spot_creds.get('SessionToken'),
            ).client("ec2", region_name=_rb_cluster.region or "ap-south-1")
            _spot_ec2.terminate_instances(InstanceIds=[_terminate_id])
            logger.info(
                f"[rollback] Terminated orphan spot {_terminate_id} "
                f"(action {wa.id})"
            )
            wa_meta['rollback_terminated_spot'] = _terminate_id
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
        if _redis:
            # Try to acquire execution lock to prevent overlapping Celery runs (Race Condition fix)
            if not _redis.set("lock:workers.auto_rebalancer", "1", nx=True, ex=300):
                logger.info("Auto-rebalancer already running, skipping this scheduled run.")
                db.close()
                return
    except Exception:
        _redis = None

    try:
        # ── STALE ACTION EXPIRY ───────────────────────────────────────────────
        # Actions stuck in in_progress or waiting_agent for >45 min are orphaned:
        # spot node never joined K8s, agent restarted, EC2 launch failed silently,
        # or drain timed out.  Expire them so they don't block new migrations
        # forever and so the history card shows an honest 'failed' entry instead
        # of a ghost 'In Progress' badge.
        _stale_cutoff = datetime.utcnow() - timedelta(minutes=45)
        _stale_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            RebalancingAction.started_at < _stale_cutoff,
        ).all()
        for _stale in _stale_actions:
            _stuck_min = int((datetime.utcnow() - _stale.started_at).total_seconds() / 60) if _stale.started_at else 0
            _stale.status = 'failed'
            _stale.error_message = (
                f"Action timed out after {_stuck_min} min in state '{_stale.status}'. "
                f"Possible causes: spot node never joined (InsufficientInstanceCapacity), "
                f"K8s agent disconnected, EC2 launch failed silently, or drain blocked by PDB. "
                f"Rebalancer will retry on next eligible cycle."
            )
            _stale.completed_at = datetime.utcnow()
            if _stale.started_at:
                _stale.duration_seconds = int(
                    (datetime.utcnow() - _stale.started_at).total_seconds()
                )
            logger.warning(
                f"[auto_rebalancer] Expired stale action {_stale.id} "
                f"({_stale.source_pool} → {_stale.target_pool}) — "
                f"stuck {_stuck_min} min in status that was '{_stale.status}' "
                f"(started {_stale.started_at})"
            )
        if _stale_actions:
            db.commit()
            logger.warning(
                f"[auto_rebalancer] Expired {len(_stale_actions)} stale RebalancingAction(s) "
                f"that exceeded the 45-min timeout."
            )

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
                    # Load opt_settings once for this action's cluster (used for join timeout)
                    try:
                        from backend.models.cluster import ClusterOptimizationSettings as _COSS
                        _wa_opt = db.query(_COSS).filter(_COSS.cluster_id == _wa.cluster_id).first()
                    except Exception:
                        _wa_opt = None
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
                        # Prefer the specific replacement instance recorded at Phase 1
                        # launch — prevents grabbing a concurrent action's spot node.
                        _replacement_id_pinned = _wa_meta.get('replacement_spot_instance_id')
                        if _replacement_id_pinned:
                            _newest_spot = db.query(Instance).filter(
                                Instance.cluster_id == _wa.cluster_id,
                                Instance.lifecycle == InstanceLifecycle.SPOT,
                                Instance.state == 'running',
                                Instance.instance_id == _replacement_id_pinned[:20],
                            ).first()
                            if not _newest_spot:
                                # Not yet running (still pending) — don't fall through to newest-by-date
                                # as that could grab a different action's replacement node
                                logger.debug(
                                    f"[auto_rebalancer] Action {_wa.id}: pinned replacement "
                                    f"{_replacement_id_pinned[:12]} not yet running — waiting"
                                )
                                continue
                        else:
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
                    _join_timeout_cfg = getattr(_wa_opt, 'spot_join_timeout_minutes', None) if _wa_opt else None
                    _SPOT_WAIT_TIMEOUT_S = (_join_timeout_cfg * 60) if (_join_timeout_cfg and _join_timeout_cfg > 0) else (30 * 60)

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
                                            "rebalancing_action_id": str(_wa.id),
                                            "purpose": "protect_replacement_node",
                                        },
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
                            # Timeout: spot replacement did not join K8s in time.
                            # For direct EC2 launch (non-Karpenter S2S): the replacement EC2
                            # is running in AWS but kubelet never started (likely missing user-data /
                            # IAM issue). Terminate the orphan EC2 and FAIL the action — do NOT
                            # drain the source node without a working replacement.
                            if _direct_launch:
                                _orphan_id = _wa_meta.get('replacement_spot_instance_id')
                                if _orphan_id:
                                    try:
                                        _do_rollback_terminate_orphan_spot(
                                            _wa, _wa_meta, db
                                        )
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: direct-launch "
                                            f"orphan {_orphan_id} terminated (kubelet never joined K8s)"
                                        )
                                    except Exception as _orp_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: orphan termination "
                                            f"failed: {_orp_err} — manual cleanup of {_orphan_id} required"
                                        )
                                logger.error(
                                    f"[auto_rebalancer] Action {_wa.id}: direct spot node "
                                    f"did not join cluster after {int(_spot_wait_elapsed)}s — "
                                    f"failing action. Likely cause: missing user-data (grant "
                                    f"ec2:DescribeInstanceAttribute + ec2:DescribeLaunchTemplateVersions)"
                                )
                                _wa.status = 'failed'
                                _wa.error_message = (
                                    f"Spot node did not join cluster after {int(_spot_wait_elapsed)}s. "
                                    f"Likely cause: EKS bootstrap script not copied to new node. "
                                    f"Grant ec2:DescribeInstanceAttribute and ec2:DescribeLaunchTemplateVersions "
                                    f"to the cross-account IAM role and retry."
                                )
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                db.commit()
                                continue

                            # Karpenter (non-direct) timeout: check if other nodes exist
                            # to absorb workloads before proceeding.
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
                                    # TASK-1.1: termination_mode replaces decrement_asg boolean.
                                    # "replacement" = detach-not-decrement; ASG DesiredCapacity stays
                                    # unchanged so AWS auto-launches a new spot in the same group.
                                    "termination_mode": "replacement",
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
                        _READINESS_GRACE_S = 20   # 20 seconds minimum after kubectl delete node (90s spot-stabilisation wait already happened before Phase 2)
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

                        # Single-path terminate — no fallbacks.
                        # Using a fallback (ASG fail → direct EC2) is what caused cluster growth:
                        # direct EC2 removes the instance but leaves ASG desired=1, so ASG
                        # auto-relaunches an OD replacement when processes are resumed.
                        # Rule: if the node is in an ASG, use ASG terminate ONLY.
                        #       if the node is NOT in an ASG (Karpenter-managed), use direct EC2 ONLY.
                        # On ANY failure — log the error, mark ec2_terminate_failed, do NOT retry.
                        try:
                            _stored_asg_for_term = _wa_meta.get('asg_name_used')

                            if _stored_asg_for_term:
                                # ── ASG-managed node: suspend Launch → detach → terminate
                                # → decrement DesiredCapacity → resume Launch.
                                # CRITICAL: We decrement DesiredCapacity BEFORE resuming Launch
                                # so the ASG doesn't auto-launch a new OD replacement.
                                # The spot replacement is already running at this point.
                                _asg_wa = _b3wa.client("autoscaling",
                                                       region_name=_term_region, **_wa_creds)
                                _ec2_wa_term = _b3wa.client("ec2",
                                                            region_name=_term_region, **_wa_creds)
                                _asg_suspend_lock = f"asg:suspend_lock:{_stored_asg_for_term}"
                                with _redis.lock(_asg_suspend_lock, timeout=60, blocking_timeout=65):
                                    # Step 1: Suspend Launch to prevent auto-scaling during operation
                                    _asg_wa.suspend_processes(
                                        AutoScalingGroupName=_stored_asg_for_term,
                                        ScalingProcesses=['Launch'],
                                    )
                                    try:
                                        # Step 2: Get current desired/min FIRST so we can
                                        # decrement even if later steps fail.
                                        _asg_info = _asg_wa.describe_auto_scaling_groups(
                                            AutoScalingGroupNames=[_stored_asg_for_term]
                                        )
                                        _asg_groups = _asg_info.get('AutoScalingGroups', [])
                                        _cur_desired = _asg_groups[0]['DesiredCapacity'] if _asg_groups else 1
                                        _cur_min = _asg_groups[0]['MinSize'] if _asg_groups else 0

                                        # Step 3: Detach without decrement — non-fatal.
                                        # EKS Managed Node Groups auto-terminate the EC2 when
                                        # 'kubectl delete node' runs, which removes the instance
                                        # from the ASG before we reach here. In that case
                                        # detach_instances throws a ValidationError. We catch it
                                        # and continue — terminate + decrement still run.
                                        try:
                                            _asg_wa.detach_instances(
                                                InstanceIds=[_wa_instance_id],
                                                AutoScalingGroupName=_stored_asg_for_term,
                                                ShouldDecrementDesiredCapacity=False,
                                            )
                                        except Exception as _detach_err:
                                            logger.warning(
                                                f"[auto_rebalancer] detach_instances failed for "
                                                f"{_wa_instance_id} (likely already removed by EKS MNG "
                                                f"after kubectl delete node): {_detach_err} — "
                                                f"continuing with EC2 terminate + capacity decrement"
                                            )

                                        # Step 4: Terminate the EC2 instance — idempotent if
                                        # EKS MNG already terminated it (returns success).
                                        try:
                                            _ec2_wa_term.terminate_instances(InstanceIds=[_wa_instance_id])
                                        except Exception as _term_ec2_err:
                                            logger.warning(
                                                f"[auto_rebalancer] terminate_instances failed for "
                                                f"{_wa_instance_id}: {_term_ec2_err} — "
                                                f"continuing with capacity decrement"
                                            )

                                        # Step 5: ALWAYS decrement DesiredCapacity regardless of
                                        # whether Steps 3–4 succeeded.  This is the critical fix:
                                        # if we skip the decrement, ASG desired stays at N while
                                        # only N-1 instances are running → ASG auto-launches an
                                        # OD replacement when Launch is resumed → cluster grows.
                                        #
                                        # Cluster size math: we launched 1 spot BEFORE cordon,
                                        # so total = N. After OD terminates + desired--, ASG
                                        # desired = N-1, spot nodes = 1 more → size stays N. ✓
                                        #
                                        # When desired reaches 0 (all OD converted):
                                        #   • Cluster Autoscaler can still raise desired from 0
                                        #     when pending pods exist (traffic spike) → ASG
                                        #     launches new OD → rebalancer converts to spot
                                        #     within the next 15s cycle automatically.
                                        #   • If CA is not installed: user scales manually or
                                        #     directly increases desired — rebalancer handles it.
                                        _new_desired = max(0, _cur_desired - 1)
                                        _new_min = min(_cur_min, _new_desired)
                                        _asg_wa.update_auto_scaling_group(
                                            AutoScalingGroupName=_stored_asg_for_term,
                                            MinSize=_new_min,
                                            DesiredCapacity=_new_desired,
                                        )
                                        if _new_desired == 0:
                                            logger.info(
                                                f"[auto_rebalancer] ASG '{_stored_asg_for_term}' "
                                                f"fully converted to spot: desired=0. "
                                                f"Cluster runs on spot-only. Any new OD added "
                                                f"(CA/manual scale-up) will be auto-converted."
                                            )
                                        else:
                                            logger.info(
                                                f"[auto_rebalancer] ASG '{_stored_asg_for_term}' capacity "
                                                f"decremented: desired {_cur_desired}→{_new_desired}, "
                                                f"min {_cur_min}→{_new_min}"
                                            )
                                    finally:
                                        # Step 6: Always re-enable Launch
                                        _asg_wa.resume_processes(
                                            AutoScalingGroupName=_stored_asg_for_term,
                                            ScalingProcesses=['Launch'],
                                        )
                                _terminated = True
                                logger.info(
                                    f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                    f"via ASG detach+EC2 terminate (DesiredCapacity decremented, "
                                    f"cluster size maintained, action {_wa.id} post-drain)"
                                )
                            else:
                                # ── Non-ASG node (Karpenter-managed): direct EC2 ONLY ─────
                                _ec2_wa = _b3wa.client("ec2",
                                                       region_name=_term_region, **_wa_creds)
                                _ec2_wa.terminate_instances(InstanceIds=[_wa_instance_id])
                                _terminated = True
                                logger.info(
                                    f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                    f"via direct EC2 API (non-ASG node, action {_wa.id} post-drain)"
                                )

                            _wa_meta['step_5_old_node_terminated'] = datetime.utcnow().isoformat()
                            # ── Immediately mark source instance as terminated in DB ──
                            # Without this, the rebalancer sees it as ON_DEMAND on the
                            # next 15s cycle and launches ANOTHER replacement → cluster growth.
                            try:
                                _src_db_inst = db.query(Instance).filter(
                                    Instance.instance_id == _wa_instance_id
                                ).first()
                                if _src_db_inst:
                                    _src_db_inst.state = 'terminated'
                                    db.flush()
                                    logger.info(
                                        f"[auto_rebalancer] Marked {_wa_instance_id} as "
                                        f"terminated in DB (prevents cluster growth)"
                                    )
                            except Exception as _term_db_err:
                                logger.warning(
                                    f"[auto_rebalancer] Failed to mark source instance "
                                    f"terminated in DB: {_term_db_err}"
                                )
                            # Also clear the per-instance rebalancing cooldown key so discovery
                            # can re-register this instance if it somehow reappears (unlikely).
                            try:
                                _redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")
                            except Exception:
                                pass

                        except Exception as _term_err:
                            _wa_meta['ec2_terminate_failed'] = True
                            logger.error(
                                f"[auto_rebalancer] EC2 terminate FAILED for {_wa_instance_id}: "
                                f"{_term_err} — no fallback applied, cluster state unchanged. "
                                f"Manual intervention required."
                            )
                            # Set a 90-min Redis cooldown so the rebalancer doesn't
                            # immediately retry the same source instance (cluster growth guard).
                            try:
                                _redis.set(
                                    f"spot:term_failed:{_wa_instance_id}", "1", ex=5400
                                )
                            except Exception:
                                pass
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
                        # Fallback: parse from target_pool string for old actions that
                        # pre-date the 'target_az' metadata key being stored at creation.
                        _target_az = _wa_meta.get("target_az") or (
                            _wa.target_pool.split(':')[1]
                            if _wa.target_pool and ':' in _wa.target_pool else ""
                        )
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
            # Load optimization settings once per cluster (used for cooldown + other logic)
            _opt_settings = db.query(ClusterOptimizationSettings).filter(
                ClusterOptimizationSettings.cluster_id == cluster.id
            ).first()

            logger.debug(f"[auto_rebalancer] >>> Processing cluster {cluster.name} (id={cluster.id})")

            # ── PER-CLUSTER INTERVAL GATE ────────────────────────────────────
            # Each cluster can configure its own check frequency (default 15s).
            # The Celery beat fires every 15s; this gate prevents re-processing
            # clusters more frequently than their configured interval.
            _check_interval = max(15, int(getattr(_opt_settings, 'check_interval_seconds', 15) or 15))
            _last_check_key = f"spot:last_check:{cluster.id}"
            try:
                if _redis and _check_interval > 15 and _redis.exists(_last_check_key):
                    continue  # interval key still alive → not time yet
            except Exception:
                pass
            try:
                if _redis and _check_interval > 15:
                    _redis.setex(_last_check_key, _check_interval, "1")
            except Exception:
                pass

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
                                _Inst.lifecycle == InstanceLifecycle.ON_DEMAND,
                                _Inst.instance_id.like('i-%')
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

            logger.info(f"[auto_rebalancer] CHECKPOINT-A cluster={cluster.name}")
            # ── GHOST INSTANCE CLEANUP ──────────────────────────────────────
            # Remove placeholder records (instance_id NOT like 'i-%') that were
            # created before the metrics.py guard was added. These ghost instances
            # pollute OD queries (blocking S2S) and show "unknown" in the UI.
            try:
                _ghost_updated = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    ~Instance.instance_id.like('i-%'),
                    ~Instance.instance_id.like('ip-%'),
                ).update({'state': 'terminated'}, synchronize_session=False)
                if _ghost_updated:
                    db.flush()
                    logger.info(
                        f"[auto_rebalancer] Cleaned up {_ghost_updated} ghost placeholder "
                        f"instance(s) for cluster {cluster.name}"
                    )
            except Exception as _ghost_err:
                logger.warning(f"[auto_rebalancer] Ghost cleanup failed for {cluster.name}: {_ghost_err}")
            # ── STALE ip- PLACEHOLDER CLEANUP ──────────────────────────────
            # ip- records (K8s hostname-style IDs) are stale when no running i-
            # instance has a matching node_name. Without this cleanup, stale OD
            # placeholders (e.g. ip-192-168-70-251) inflate _od_count and block S2S.
            try:
                _ip_placeholders = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.instance_id.like('ip-%'),
                ).all()
                if _ip_placeholders:
                    _real_node_names = set(
                        r[0] for r in db.query(Instance.node_name).filter(
                            Instance.cluster_id == cluster.id,
                            Instance.state == 'running',
                            Instance.instance_id.like('i-%'),
                            Instance.node_name.isnot(None),
                        ).all()
                    )
                    _stale_ip_count = 0
                    for _ip_rec in _ip_placeholders:
                        _ip_prefix = _ip_rec.instance_id  # e.g. 'ip-192-168-70-251'
                        _matched = any(
                            nm and (nm == _ip_prefix or nm.startswith(_ip_prefix + '.'))
                            for nm in _real_node_names
                        )
                        if not _matched:
                            _ip_rec.state = 'terminated'
                            _stale_ip_count += 1
                    if _stale_ip_count:
                        db.flush()
                        logger.info(
                            f"[auto_rebalancer] Cleaned up {_stale_ip_count} stale ip- "
                            f"placeholder(s) for cluster {cluster.name} "
                            f"(no matching running i- node_name)"
                        )
            except Exception as _ip_err:
                logger.warning(f"[auto_rebalancer] Stale ip- cleanup failed for {cluster.name}: {_ip_err}")
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
                # Daily limit is designed to prevent excessive SPOT→SPOT churn.
                # OD→SPOT conversions are always allowed — that's the core purpose
                # of the platform and should never be blocked by the churn limiter.
                # Use raw SQL to ensure fresh read (bypasses ORM identity cache).
                try:
                    _od_row = db.execute(
                        "SELECT COUNT(*) FROM instances "
                        "WHERE cluster_id = :cid AND state = 'running' "
                        "AND instance_id LIKE 'i-%' "
                        "AND lifecycle NOT IN ('spot', 'SPOT')",
                        {"cid": cluster.id}
                    ).scalar()
                    _pre_od_count = int(_od_row or 0)
                except Exception:
                    _pre_od_count = 0
                if _pre_od_count == 0:
                    # No OD nodes — only S2S work remains. S2S has its own per-node
                    # daily limit check (line ~3044) so do NOT continue here.
                    # Log the state for observability but fall through to S2S section.
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name}: daily limit reached "
                        f"({recent_rebalances}/{max_rebalances}) — no OD nodes, S2S will "
                        f"apply its own limit check"
                    )
                logger.info(
                    f"[auto_rebalancer] Daily limit reached ({recent_rebalances}/{max_rebalances}) "
                    f"but cluster {cluster.name} has {_pre_od_count} OD node(s) — "
                    f"bypassing limit for OD→spot conversion"
                )

            logger.info(f"[auto_rebalancer] CHECKPOINT-B cluster={cluster.name} recent={recent_rebalances}/{max_rebalances}")
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
                Instance.instance_id.like('i-%'),  # exclude ghost placeholders
            ).count()
            _od_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',
                Instance.instance_id.like('i-%'),  # exclude ghost placeholders
            ).count()
            if _total_nodes == 0:
                # Completely empty cluster — nothing to rebalance
                logger.info(f"[auto_rebalancer] Cluster {cluster.name}: no running instances — skipping")
                continue

            if _total_nodes == 1 and _od_count == 0:
                # Single SPOT node — cluster is already optimized.
                # Fall through to the S2S section which has its own safety checks
                # (S2S will not drain the last node without a confirmed replacement).
                logger.info(
                    f"[auto_rebalancer] Cluster {cluster.name}: 1 spot node, 0 OD nodes "
                    f"— skipping last-node guard, proceeding to S2S diversification"
                )

            elif _total_nodes <= 1:
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
                                Instance.instance_id.like('i-%')
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
                                Instance.instance_id.like('i-%')
                            ).first()
                            if _any_od:
                                _specs_ln = _INSTANCE_VCPU_MEM.get(_any_od.instance_type, (2, 8))
                                _ranked_ln = PoolRankingService(db, _redis).rank_pools_for_size(
                                    vcpu=_specs_ln[0], memory_gb=float(_specs_ln[1]),
                                    region=cluster.region or "ap-south-1", limit=6
                                )
                                _types_ln = [p.pool.instance_type for p in (_ranked_ln or [])] or [_any_od.instance_type]
                                _new_spot_id, _ln_actual_type, _ln_actual_az, _ln_launch_err, _ln_skipped = _launch_spot_instance_direct(
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
                    # ── Cluster-level recovery cap: max 1 recovery per cluster per cycle ──
                    _cluster_recovery_key = f"spot:recovery:cluster:{cluster.id}"
                    if _redis and _redis.exists(_cluster_recovery_key):
                        logger.debug(
                            f"[auto_rebalancer] Spot recovery: cluster {cluster.name} "
                            f"already has a recovery in progress this cycle — skipping"
                        )
                    else:
                        # Lookback: only check the last 24h (not 7 days) to avoid
                        # re-triggering recovery for long-stale historical launches.
                        _direct_launches = db.query(_AA_REC).filter(
                            _AA_REC.cluster_id == cluster.id,
                            _AA_REC.action_type == _AAT_REC.PATCH_KARPENTER_NODEPOOL,
                            _AA_REC.payload.contains({"direct_ec2_launch": True}),
                            _AA_REC.created_at >= datetime.utcnow() - timedelta(hours=24),
                        ).order_by(_AA_REC.created_at.desc()).all()

                        for _dl in _direct_launches:
                            _dl_payload = _dl.payload or {}
                            _launched_spot_id = _dl_payload.get("new_ec2_instance_id")
                            if not _launched_spot_id:
                                continue

                            # Per-instance dedup: recovery already in progress?
                            _recovery_key = f"spot:recovery:{_launched_spot_id}"
                            if _redis and _redis.exists(_recovery_key):
                                continue

                            # Only act if discovery has seen this instance (else still launching)
                            _spot_inst = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.instance_id == _launched_spot_id,
                            ).first()
                            if not _spot_inst:
                                continue  # Not yet in DB — still launching
                            if _spot_inst.state == 'running':
                                continue  # Still healthy in DB

                            # ── AWS VERIFY: never trust DB alone for termination decision ──
                            # DB may be stale — confirm the instance is ACTUALLY terminated
                            # in AWS before launching a replacement. A false positive here
                            # causes cascade launches (the bug that spawned 5 instances).
                            try:
                                from backend.utils.aws.asg import get_assumed_credentials as _gac_verify
                                import boto3 as _b3_verify
                                _vc = _gac_verify(cluster, db)
                                _verify_ec2 = _b3_verify.Session(
                                    aws_access_key_id=_vc.get('AccessKeyId'),
                                    aws_secret_access_key=_vc.get('SecretAccessKey'),
                                    aws_session_token=_vc.get('SessionToken'),
                                ).client("ec2", region_name=cluster.region or "ap-south-1")
                                _verify_resp = _verify_ec2.describe_instances(
                                    InstanceIds=[_launched_spot_id]
                                )
                                _verify_reservations = _verify_resp.get("Reservations", [])
                                if _verify_reservations:
                                    _aws_state = (
                                        _verify_reservations[0]
                                        .get("Instances", [{}])[0]
                                        .get("State", {})
                                        .get("Name", "unknown")
                                    )
                                    if _aws_state == "running":
                                        # DB is stale — heal it and skip recovery
                                        _spot_inst.state = "running"
                                        db.flush()
                                        logger.info(
                                            f"[auto_rebalancer] Spot recovery: {_launched_spot_id} "
                                            f"is RUNNING in AWS (DB was stale) — healed DB, skipping recovery"
                                        )
                                        continue
                                    elif _aws_state not in ("terminated", "shutting-down"):
                                        # Pending/stopping — give it time, don't recovery yet
                                        logger.debug(
                                            f"[auto_rebalancer] Spot recovery: {_launched_spot_id} "
                                            f"AWS state={_aws_state} — waiting, skip recovery this cycle"
                                        )
                                        continue
                                    # else: AWS confirms terminated → proceed with recovery
                            except Exception as _verify_err:
                                logger.warning(
                                    f"[auto_rebalancer] Spot recovery: AWS verify failed for "
                                    f"{_launched_spot_id}: {_verify_err} — skipping recovery (conservative)"
                                )
                                continue  # Skip if we can't confirm termination

                            # Instance is terminated — was it us (intentional TERMINATE_NODE)?
                            _our_termination = db.query(_AA_REC).filter(
                                _AA_REC.cluster_id == cluster.id,
                                _AA_REC.action_type == _AAT_REC.TERMINATE_NODE,
                                _AA_REC.payload.contains({"instance_id": _launched_spot_id}),
                                _AA_REC.status == _AAS_REC.COMPLETED,
                            ).first()
                            if _our_termination:
                                continue  # Intentional replacement — no recovery needed

                            # Find a running instance to clone user-data / subnet / SG from
                            _ref_od = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.state == 'running',
                                Instance.instance_id.like('i-%'),
                            ).first()
                            if not _ref_od:
                                logger.warning(
                                    f"[auto_rebalancer] Spot recovery: no running reference "
                                    f"instance for cluster {cluster.name} — skipping"
                                )
                                break  # Nothing to clone from; try again next cycle

                            logger.info(
                                f"[auto_rebalancer] Spot recovery: {_launched_spot_id} confirmed "
                                f"terminated by AWS — relaunching replacement for {cluster.name}"
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
                            _new_spot_id, _rec_actual_type, _rec_actual_az, _rec_launch_err, _rec_skipped = _launch_spot_instance_direct(
                                db, cluster,
                                source_instance_id=_ref_od.instance_id,
                                target_instance_types=_types_rec,
                                target_az=_spot_inst.az or "",
                                region=cluster.region or "ap-south-1",
                            )
                            if _new_spot_id:
                                if _redis:
                                    _redis.setex(_recovery_key, 3600, _new_spot_id)       # 1h per-instance
                                    _redis.setex(_cluster_recovery_key, 120, _new_spot_id)  # 2 min cluster cap
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
                            break  # Only 1 recovery per cluster per cycle
                except Exception as _rec_err:
                    logger.warning(
                        f"[auto_rebalancer] Spot recovery check failed for {cluster.name}: {_rec_err}"
                    )

            logger.info(f"[auto_rebalancer] CHECKPOINT-C cluster={cluster.name}")
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
                # Cooldown: user-configured (cooldown_override_minutes), default 60 min
                _cooldown_cfg = getattr(_opt_settings, 'cooldown_override_minutes', None) if _opt_settings else None
                _COOLDOWN = (_cooldown_cfg * 60) if (_cooldown_cfg and _cooldown_cfg > 0) else 3600
                if elapsed < _COOLDOWN:
                    # Cooldown prevents excessive S2S churn. OD→SPOT conversions always
                    # bypass it — converting OD to spot is the platform's primary purpose.
                    try:
                        _cd_od = db.execute(
                            "SELECT COUNT(*) FROM instances WHERE cluster_id = :cid "
                            "AND state = 'running' AND lifecycle NOT IN ('spot', 'SPOT')",
                            {"cid": cluster.id}
                        ).scalar()
                        _cd_od = int(_cd_od or 0)
                    except Exception:
                        _cd_od = 0
                    if _cd_od == 0:
                        # No OD nodes — check for diversification violations that also bypass
                        _cd_diversify_bypass = False
                        try:
                            _cd_opt_div = db.query(ClusterOptimizationSettings).filter_by(
                                cluster_id=cluster.id
                            ).first()
                            if getattr(_cd_opt_div, 'diversify_pools', False):
                                _cd_running = db.query(Instance).filter(
                                    Instance.cluster_id == cluster.id,
                                    Instance.state == 'running',
                                ).all()
                                _cd_pool_dist: dict = {}
                                for _cdr in _cd_running:
                                    if _cdr.instance_type and _cdr.az:
                                        _k = (_cdr.instance_type, _cdr.az)
                                        _cd_pool_dist[_k] = _cd_pool_dist.get(_k, 0) + 1
                                _cd_diversify_bypass = any(v > 1 for v in _cd_pool_dist.values())
                        except Exception:
                            pass
                        if not _cd_diversify_bypass:
                            logger.info(
                                f"[auto_rebalancer] Cluster {cluster.name}: strict {_COOLDOWN}s cooldown "
                                f"({int(_COOLDOWN - elapsed)}s remaining)"
                            )
                            continue
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: cooldown active "
                            f"({int(_COOLDOWN - elapsed)}s remaining) but diversify violation detected "
                            f"— bypassing cooldown for S2S diversification fix"
                        )
                    else:
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: cooldown active "
                            f"({int(_COOLDOWN - elapsed)}s remaining) but {_cd_od} OD node(s) "
                            f"— bypassing cooldown for OD→SPOT conversion"
                        )

            # Re-queue only the OLDEST deferred action (1 at a time per cluster)
            oldest_deferred = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'deferred'
            ).order_by(RebalancingAction.started_at).first()
            if oldest_deferred:
                # OD nodes take priority over deferred S2S actions — check first.
                try:
                    _def_od = db.execute(
                        "SELECT COUNT(*) FROM instances WHERE cluster_id = :cid "
                        "AND state = 'running' AND lifecycle NOT IN ('spot', 'SPOT')",
                        {"cid": cluster.id}
                    ).scalar()
                    _def_od = int(_def_od or 0)
                except Exception:
                    _def_od = 0
                if _def_od > 0:
                    logger.info(
                        f"[auto_rebalancer] Skipping deferred action {oldest_deferred.id} re-queue: "
                        f"{_def_od} OD node(s) take priority for cluster {cluster.name}"
                    )
                    # Fall through to OD instance processing below
                else:
                    oldest_deferred.status = 'in_progress'
                    oldest_deferred.started_at = datetime.utcnow()
                    logger.info(f"Re-queuing deferred action {oldest_deferred.id} for cluster {cluster.name}")
                    # Don't create new actions this cycle — retry the deferred one first
                    continue

            logger.info(f"[auto_rebalancer] CHECKPOINT-D cluster={cluster.name}")
            # Find on-demand instances that should be migrated to spot
            # IMPORTANT: state='running' filter prevents terminated OD instances
            # (instances already replaced in a previous cycle whose DB record hasn't
            # been cleaned up yet) from being retargeted — which caused an infinite loop
            # where the same "dead" OD node was queued for rebalancing over and over.
            on_demand_instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',   # Only target running OD nodes
                Instance.instance_id.like('i-%'),  # exclude ghost placeholder instances
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
                    # No OD instances found — but SPOT instances may still need S2S
                    # diversification or risk-based migration. Only truly skip if there
                    # are no running instances at all (empty cluster).
                    _any_running = db.query(Instance).filter(
                        Instance.cluster_id == cluster.id,
                        Instance.state == 'running',
                    ).count()
                    if _any_running == 0:
                        logger.info(
                            f"[auto_rebalancer] No running instances for cluster {cluster.name} "
                            f"— skipping rebalancing this cycle"
                        )
                        continue
                    # else: fall through — S2S checks will run on spot instances below

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

            logger.info(f"[auto_rebalancer] CHECKPOINT-E cluster={cluster.name} od={len(on_demand_instances)}")
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
                logger.info(f"[auto_rebalancer] CHECKPOINT-F S2S diversify_s2s={_diversify_s2s} cluster={cluster.name}")
                _diversify_fam_cap_pct = getattr(_opt_s2s, 'max_family_diversification_cap_pct', 40) or 40
                _diversify_fam_cap_ratio = _diversify_fam_cap_pct / 100.0
                import math as _math_s2s

                # Load risk strategy (risk ceiling + tradeoff %) for S2S decisions
                try:
                    from backend.models.cluster import OptimizationStrategy as _OptS_s2s
                    _opt_strat_s2s = db.query(_OptS_s2s).filter_by(cluster_id=cluster.id).first()
                    _risk_ceil_s2s = (getattr(_opt_strat_s2s, 'risk_ceiling_percent', 25) or 25) / 100.0
                    _tradeoff_pct_s2s = (getattr(_opt_strat_s2s, 'risk_savings_tradeoff_pct', 20) or 20) / 100.0
                except Exception:
                    _risk_ceil_s2s = 0.25
                    _tradeoff_pct_s2s = 0.20
                # Apply regional market factor to S2S risk ceiling (clamped 0.8–1.2)
                try:
                    _mf_raw_s2s = _redis.get(f"market_factor:{cluster.region or 'ap-south-1'}")
                    _risk_ceil_s2s *= float(_mf_raw_s2s) if _mf_raw_s2s else 1.0
                except Exception:
                    pass

                # Pool distribution across ALL currently running nodes
                _all_running_s2s = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()
                # pool_counts_s2s: (instance_type, az) → count for pool-level uniqueness
                _pool_counts_s2s: dict = {}
                _fam_counts_s2s: dict = {}  # kept for legacy risk-check pass
                for _sri in _all_running_s2s:
                    if _sri.instance_type and _sri.az:
                        _spk = (_sri.instance_type, _sri.az)
                        _pool_counts_s2s[_spk] = _pool_counts_s2s.get(_spk, 0) + 1
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

                    # Active-action guard: only 1 migration at a time per cluster
                    _active_s2s = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent'])
                    ).first()
                    if _active_s2s:
                        break
                    # Daily limit guard: diversify violations always bypass (correctness,
                    # not churn); risk-based S2S is subject to the per-cluster limit.
                    _s2s_is_diversify = False
                    if _diversify_s2s and _sp_inst.instance_type and _sp_inst.az:
                        _sp_pool_key_s2s_pre = (_sp_inst.instance_type, _sp_inst.az)
                        _s2s_is_diversify = _pool_counts_s2s.get(_sp_pool_key_s2s_pre, 0) > 1
                    if recent_rebalances >= max_rebalances and not _s2s_is_diversify:
                        break  # over limit + no diversify violation → skip

                    _s2s_trigger_reason = None
                    _cur_risk_s2s = None  # may remain None if Check 2 is skipped (diversify trigger)

                    # ── Check 0: Opportunistic better-pool trigger ────────────────
                    # If a pool exists that is BOTH cheaper (higher savings) AND safer
                    # (lower risk) than the current pool, always migrate — no other
                    # condition required. Minimum deltas prevent micro-fluctuation churn.
                    _S2S_OPP_RISK_DELTA  = 0.05   # pool must be ≥5pp lower risk
                    _S2S_OPP_SAV_DELTA   = 0.01   # pool must be ≥1pp higher savings
                    if not _s2s_trigger_reason and _sp_inst.instance_type:
                        try:
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM_opp
                            from backend.services.pool_ranking_service import PoolRankingService as _PRS_opp
                            _opp_specs = _IVM_opp.get(_sp_inst.instance_type, (2, 8))
                            _opp_ranked = _PRS_opp(db, _redis).rank_pools_for_size(
                                vcpu=_opp_specs[0], memory_gb=float(_opp_specs[1]),
                                region=cluster.region or 'ap-south-1', limit=10
                            )
                            if _opp_ranked:
                                _opp_cur = next(
                                    (_rp for _rp in _opp_ranked
                                     if _rp.pool.instance_type == _sp_inst.instance_type and
                                     (_rp.pool.az or "") == (_sp_inst.az or "")),
                                    None
                                )
                                if _opp_cur:
                                    _opp_cur_risk = _opp_cur.risk_probability
                                    _opp_cur_sav  = _opp_cur.predicted_savings
                                    _opp_better = next(
                                        (_rp for _rp in _opp_ranked
                                         if (_rp.pool.instance_type, _rp.pool.az or "") !=
                                            (_sp_inst.instance_type, _sp_inst.az or "")
                                         and _rp.risk_probability <= _opp_cur_risk - _S2S_OPP_RISK_DELTA
                                         and _rp.predicted_savings >= _opp_cur_sav + _S2S_OPP_SAV_DELTA),
                                        None
                                    )
                                    if _opp_better:
                                        _cur_risk_s2s = _opp_cur_risk
                                        _s2s_trigger_reason = (
                                            f'opportunistic: {_opp_better.pool.instance_type}:{_opp_better.pool.az} '
                                            f'risk {_opp_cur_risk:.2f}→{_opp_better.risk_probability:.2f} '
                                            f'sav {_opp_cur_sav:.2f}→{_opp_better.predicted_savings:.2f}'
                                        )
                                        logger.info(
                                            f"[auto_rebalancer] S2S opportunistic trigger: "
                                            f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                            f"— {_s2s_trigger_reason}"
                                        )
                        except Exception as _opp_err:
                            logger.debug(f'[auto_rebalancer] S2S opportunistic check: {_opp_err}')

                    # ── Check 1: Diversify violation (pool-level) ─────────────────
                    # Pool = (instance_type, az). If >1 node shares the same pool, trigger S2S.
                    if _diversify_s2s and _sp_inst.instance_type and _sp_inst.az:
                        _sp_pool_key_s2s = (_sp_inst.instance_type, _sp_inst.az)
                        _sp_pool_count = _pool_counts_s2s.get(_sp_pool_key_s2s, 0)
                        if _sp_pool_count > 1:
                            _s2s_trigger_reason = (
                                f'diversify_pools: duplicate pool '
                                f'{_sp_inst.instance_type}:{_sp_inst.az} '
                                f'({_sp_pool_count} nodes)'
                            )
                            logger.info(
                                f"[auto_rebalancer] S2S diversify trigger: "
                                f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                f"— {_s2s_trigger_reason}"
                            )
                            
                        # ── Check 1.5: Diversify violation (family-level) ─────────────
                        if not _s2s_trigger_reason and _sp_inst.instance_type:
                            _f = _sp_inst.instance_type.split('.')[0]
                            _f_count = _fam_counts_s2s.get(_f, 0)
                            # Use ceiling so small clusters are handled correctly:
                            # ceil(0.40 * 3) = 2 — a family is only "over cap" when it
                            # holds strictly MORE than the ceiling limit.
                            _fam_cap_nodes = max(1, _math_s2s.ceil(_diversify_fam_cap_ratio * _total_running_s2s))
                            if _total_running_s2s > 0 and _f_count > _fam_cap_nodes:
                                _s2s_trigger_reason = (
                                    f'diversify_family: family {_f} exceeds cap '
                                    f'({_f_count}/{_total_running_s2s} > {_diversify_fam_cap_pct}%)'
                                )
                                logger.info(
                                    f"[auto_rebalancer] S2S diversify trigger: "
                                    f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                    f"— {_s2s_trigger_reason}"
                                )

                    # ── Check 2: Risk-threshold trigger (uses OptimizationStrategy) ──
                    # Fires when the node's pool risk > risk_ceiling_percent.
                    # Uses the user-configured risk ceiling (default 25%).
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
                                    (_rp.risk_probability for _rp in _sp_ranked
                                     if _rp.pool.instance_type == _sp_inst.instance_type and
                                     (_rp.pool.az or "") == (_sp_inst.az or "")),
                                    next(
                                        (_rp.risk_probability for _rp in _sp_ranked
                                         if _rp.pool.instance_type == _sp_inst.instance_type),
                                        None
                                    )
                                )
                                if _cur_risk_s2s is not None and _cur_risk_s2s > _risk_ceil_s2s:
                                    _s2s_trigger_reason = (
                                        f'risk_threshold: {_sp_inst.instance_type}:{_sp_inst.az} '
                                        f'risk={_cur_risk_s2s:.2f} > ceil={_risk_ceil_s2s:.2f}'
                                    )
                        except Exception as _rck_err:
                            logger.debug(f'[auto_rebalancer] S2S risk check: {_rck_err}')

                    if not _s2s_trigger_reason:
                        continue  # this SPOT node is fine, check the next one

                    # ── Find best target pool (pool-level uniqueness + tradeoff) ──
                    try:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM3
                        from backend.services.pool_ranking_service import PoolRankingService as _PRS3
                        _sp_specs3 = _IVM3.get(_sp_inst.instance_type, (2, 8))
                        _sp_ranked3 = _PRS3(db, _redis).rank_pools_for_size(
                            vcpu=_sp_specs3[0], memory_gb=float(_sp_specs3[1]),
                            region=cluster.region or 'ap-south-1', limit=10
                        )
                        # Current node's savings baseline (for tradeoff calc)
                        _sp_cur_savings = next(
                            (_rp.predicted_savings for _rp in _sp_ranked3
                             if _rp.pool.instance_type == _sp_inst.instance_type and
                             (_rp.pool.az or "") == (_sp_inst.az or "")),
                            0.5  # assume moderate savings if not found
                        )
                        _best_s2s_pool = None
                        # Is this a diversification-triggered S2S?
                        _is_diversify_trigger = 'diversify' in (_s2s_trigger_reason or '')
                        # Pass 1: better risk AND equal/higher savings
                        for _rp3 in _sp_ranked3:
                            _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                            _t3_f = _rp3.pool.instance_type.split('.')[0]
                            if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                continue  # never re-migrate to same pool

                            # Ceiling-based family cap: ceil(cap% × total) → each family
                            # may hold at most that many nodes. This prevents the raw-ratio
                            # check from blocking all alternatives on small clusters.
                            # e.g. 3 nodes, 40% cap → ceil(1.2)=2; adding 1 to empty family
                            # gives count=1 ≤ 2 → PASSES (was 33% > 40% raw → would block).
                            _fam_cap_nodes_tgt = max(1, _math_s2s.ceil(_diversify_fam_cap_ratio * _total_running_s2s))
                            if _diversify_s2s:
                                if _pool_counts_s2s.get(_t3_pk, 0) > 0:
                                    continue  # target pool already occupied
                                _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                    continue  # family would exceed ceiling cap

                            if (_rp3.risk_probability < (_cur_risk_s2s or 1.0) and
                                    _rp3.predicted_savings >= _sp_cur_savings):
                                _best_s2s_pool = _rp3
                                break
                        # Pass 2 (tradeoff): better risk, accept up to tradeoff% less savings.
                        # ONLY for risk-threshold trigger — opportunistic/diversify must not
                        # sacrifice savings (user condition: must be BOTH cheaper AND safer).
                        if not _best_s2s_pool and 'risk_threshold' in (_s2s_trigger_reason or ''):
                            _min_sav = _sp_cur_savings * (1 - _tradeoff_pct_s2s)
                            for _rp3 in _sp_ranked3:
                                _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                                _t3_f = _rp3.pool.instance_type.split('.')[0]
                                if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                    continue

                                if _diversify_s2s:
                                    if _pool_counts_s2s.get(_t3_pk, 0) > 0:
                                        continue
                                    _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                    if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                        continue

                                if (_rp3.risk_probability < (_cur_risk_s2s or 1.0) and
                                        _rp3.predicted_savings >= _min_sav):
                                    _best_s2s_pool = _rp3
                                    break
                        # Pass 3 (diversify any-pool): for diversification triggers, accept
                        # ANY unoccupied pool from a different family — correctness over optimality.
                        if not _best_s2s_pool and _is_diversify_trigger and _diversify_s2s:
                            for _rp3 in _sp_ranked3:
                                _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                                _t3_f = _rp3.pool.instance_type.split('.')[0]
                                if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                    continue
                                _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                # Don't migrate to a DIFFERENT node in the SAME over-represented family
                                if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                    continue
                                if _pool_counts_s2s.get(_t3_pk, 0) == 0:
                                    _best_s2s_pool = _rp3
                                    break

                        if not _best_s2s_pool:
                            # Pass 3 (OD fallback): if risk is the trigger and no spot pool
                            # qualifies, fall back to same-type on-demand to maintain capacity.
                            # Diversification violations just retry next cycle (no OD needed).
                            if 'risk_threshold' in (_s2s_trigger_reason or ''):
                                _s2s_od_src = f"{_sp_inst.instance_type}:{_sp_inst.az or cluster.region + 'a'}"
                                _s2s_od_action = RebalancingAction(
                                    cluster_id=cluster.id,
                                    trigger='auto_rebalance',
                                    source_pool=_s2s_od_src,
                                    target_pool=_s2s_od_src,  # same type, OD lifecycle
                                    status='in_progress',
                                    started_at=datetime.utcnow(),
                                    action_metadata={
                                        'reason': f'{_s2s_trigger_reason} (od_fallback)',
                                        'initiated_by': 'auto_rebalancer',
                                        'instance_id': _sp_inst.instance_id,
                                        'spot_to_spot': False,
                                        'is_od_fallback': True,
                                        'target_instance_type': _sp_inst.instance_type,
                                        'bin_packed': False,
                                    }
                                )
                                db.add(_s2s_od_action)
                                _s2s_created = True
                                logger.info(
                                    f'[auto_rebalancer] S2S OD fallback: no safer spot pool for '
                                    f'{_sp_inst.instance_id} ({_sp_inst.instance_type}) — '
                                    f'replacing with on-demand (reason={_s2s_trigger_reason})'
                                )
                            else:
                                logger.info(
                                    f'[auto_rebalancer] S2S: no qualifying target pool for '
                                    f'{_sp_inst.instance_id} (risk={_cur_risk_s2s}, '
                                    f'tradeoff={_tradeoff_pct_s2s:.0%}) — will retry next cycle'
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
            _total_running = _running_spot_count + len(on_demand_instances)
            logger.debug(
                f"[auto_rebalancer] Cluster {cluster.name}: "
                f"{_running_spot_count} running spot, {len(on_demand_instances)} remaining OD"
            )

            # ── DYNAMIC AUTOSCALER (delegated to auto_scaler.py) ──────────────
            # Capacity management is handled by backend/workers/tasks/auto_scaler.py.
            # That task runs every 30 seconds and is enabled per-cluster via the
            # `enable_ascp_auto_scaler` toggle in ClusterOptimizationSettings.
            # When the toggle is OFF (default) no automatic scaling occurs here.

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
                #
                # SAFE DEFAULT: if we cannot verify lifecycle from AWS for ANY reason
                # (no credentials, API error, invalid instance ID), SKIP this instance
                # rather than proceeding. The rebalancer will retry next cycle.
                # This prevents false spot launches from stale DB data.
                try:
                    from backend.utils.aws.asg import get_assumed_credentials as _get_creds_lv
                    _lv_creds = _get_creds_lv(cluster)
                    if not _lv_creds:
                        # No credentials → cannot verify → skip this instance for safety
                        logger.info(
                            f"[auto_rebalancer] Live check skipped for {instance.instance_id}: "
                            f"no AWS credentials available — skipping to prevent false rebalancing"
                        )
                        continue
                    # Only attempt live check for real EC2 instance IDs (i-xxx)
                    if not instance.instance_id or not instance.instance_id.startswith('i-'):
                        logger.info(
                            f"[auto_rebalancer] Live check skipped: {instance.instance_id} is not "
                            f"a real EC2 ID — skipping placeholder instance"
                        )
                        instance.state = 'terminated'
                        db.commit()
                        continue
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
                        # AWS confirmed ON_DEMAND — safe to proceed with rebalancing
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
                    # AWS verification failed — SKIP this instance (safe default).
                    # Better to miss one rebalancing cycle than to falsely grow the cluster.
                    logger.warning(
                        f"[auto_rebalancer] Live lifecycle check FAILED for {instance.instance_id}: "
                        f"{_lv_err} — skipping this instance to prevent false rebalancing"
                    )
                    continue

                # Check daily limit — OD→spot conversions always bypass (see cluster-level check above)
                if (recent_rebalances) >= max_rebalances:
                    # instance here is always OD (we're in on_demand_instances loop)
                    # so we allow it through. Only break if this instance is somehow spot.
                    if instance.lifecycle != InstanceLifecycle.ON_DEMAND:
                        logger.info(f"Hit daily limit for cluster {cluster.name}")
                        break

                # ── CLUSTER GROWTH GUARD #1: termination-failed cooldown ───────
                # If we previously tried to terminate this instance and it failed,
                # don't immediately create another action → cluster would grow.
                try:
                    if _redis.get(f"spot:term_failed:{instance.instance_id}"):
                        logger.info(
                            f"[auto_rebalancer] Skipping {instance.instance_id}: "
                            f"termination recently failed (cooldown active). "
                            f"Mark instance as orphan for manual cleanup."
                        )
                        # Mark the stuck instance as orphan so UI can surface it
                        instance.state = 'orphan'
                        db.commit()
                        continue
                except Exception:
                    pass

                # ── CLUSTER GROWTH GUARD #2: recent completed action for this instance ──
                # If a completed action already ran for this source instance in the last
                # 2 hours (e.g. terminate succeeded but DB state wasn't updated yet),
                # skip it to prevent duplicate replacements.
                try:
                    _recent_completed = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['completed', 'failed']),
                        RebalancingAction.completed_at >= datetime.utcnow() - timedelta(hours=2),
                    ).filter(
                        RebalancingAction.action_metadata.op('->>')('instance_id') == instance.instance_id
                    ).first()
                    if _recent_completed:
                        logger.info(
                            f"[auto_rebalancer] Skipping {instance.instance_id}: "
                            f"recent {_recent_completed.status} action {_recent_completed.id} "
                            f"exists (< 2h) — marking DB instance as terminated to stop growth"
                        )
                        # Source should already be gone — force DB state to terminated
                        instance.state = 'terminated'
                        db.commit()
                        continue
                except Exception as _rcq_err:
                    logger.debug(f"[auto_rebalancer] Recent action check failed: {_rcq_err}")

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
                # _opt_settings already loaded at top of cluster loop
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

                    # ── DIVERSIFY POOLS: pool-level uniqueness + 50% AZ cap ─────────
                    # Pool = (instance_type, az). Max 1 node per identical pool.
                    # c5.large:ap-south-1a and c5.large:ap-south-1b are DIFFERENT pools.
                    # AZ cap (50%) is kept to prevent all nodes concentrating in one AZ.
                    if _ranked and getattr(_opt_settings, 'diversify_pools', False):
                        from backend.models.instance import Instance as _DivInst
                        _running_insts = db.query(_DivInst).filter(
                            _DivInst.cluster_id == cluster.id,
                            _DivInst.state == 'running',
                        ).all()
                        # Build pool-count dict: (instance_type, az) → count
                        _pool_counts: dict = {}
                        _az_counts: dict = {}
                        _fam_counts: dict = {}
                        _diversify_fam_cap_pct = getattr(_opt_settings, 'max_family_diversification_cap_pct', 40) or 40
                        _diversify_fam_cap_ratio = _diversify_fam_cap_pct / 100.0
                        import math as _math_div

                        for _ri in _running_insts:
                            if _ri.instance_type and _ri.az:
                                _pk = (_ri.instance_type, _ri.az)
                                _pool_counts[_pk] = _pool_counts.get(_pk, 0) + 1
                            if _ri.az:
                                _az_counts[_ri.az] = _az_counts.get(_ri.az, 0) + 1
                            if _ri.instance_type:
                                _f = _ri.instance_type.split('.')[0]
                                _fam_counts[_f] = _fam_counts.get(_f, 0) + 1

                        # Include in-flight provisioning actions to prevent duplicate pools
                        _inflight_actions_div = []
                        try:
                            _inflight_actions_div = db.query(RebalancingAction).filter(
                                RebalancingAction.cluster_id == cluster.id,
                                RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent']),
                            ).all()
                        except Exception as _div_ia_err:
                            logger.debug(f"[auto_rebalancer] In-flight action count failed: {_div_ia_err}")
                        for _ia in _inflight_actions_div:
                            # target_pool is stored as "instance_type:az" string
                            _ia_tpool = getattr(_ia, 'target_pool', None) or ''
                            if _ia_tpool and ':' in _ia_tpool:
                                _ia_type, _ia_az = _ia_tpool.split(':', 1)
                                _pk = (_ia_type, _ia_az)
                                _pool_counts[_pk] = _pool_counts.get(_pk, 0) + 1
                                _az_counts[_ia_az] = _az_counts.get(_ia_az, 0) + 1
                                _fam_counts[_ia_type.split('.')[0]] = _fam_counts.get(_ia_type.split('.')[0], 0) + 1

                        _total_nodes_div = len(_running_insts) + len(_inflight_actions_div) + 1
                        _MAX_AZ_SHARE = 0.50

                        # Ceiling-based family cap: max nodes per family = ceil(cap% × total).
                        # Prevents raw-ratio math from blocking all new families on small clusters.
                        # Example: 3 nodes, 40% cap → ceil(1.2)=2; adding 1 to empty family
                        # gives count=1 ≤ 2 → PASSES (raw 33% < 40% also passes, consistent).
                        _fam_cap_nodes_div = max(1, _math_div.ceil(_diversify_fam_cap_ratio * _total_nodes_div))

                        _diversified = []
                        for _rp in _ranked:
                            _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                            _f = _rp.pool.instance_type.split('.')[0]
                            _az_ok = (_az_counts.get(_rp.pool.az or "", 0) + 1) / _total_nodes_div <= _MAX_AZ_SHARE
                            _fam_ok = (_fam_counts.get(_f, 0) + 1) <= _fam_cap_nodes_div

                            # Pool-level & Family-level: skip if occupied or family cap exceeded
                            if _pool_counts.get(_pk, 0) == 0 and _az_ok and _fam_ok:
                                _diversified.append(_rp)
                                if len(_diversified) >= 3:
                                    break
                        # Fallback 1: relax AZ cap, still enforce pool uniqueness & family cap
                        if not _diversified:
                            for _rp in _ranked:
                                _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                                _f = _rp.pool.instance_type.split('.')[0]
                                _fam_ok = (_fam_counts.get(_f, 0) + 1) <= _fam_cap_nodes_div
                                if _pool_counts.get(_pk, 0) == 0 and _fam_ok:
                                    _diversified.append(_rp)
                                    if len(_diversified) >= 3:
                                        break
                        # Fallback 2: relax family cap too, only enforce pool uniqueness
                        if not _diversified:
                            for _rp in _ranked:
                                _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                                if _pool_counts.get(_pk, 0) == 0:
                                    _diversified.append(_rp)
                                    if len(_diversified) >= 3:
                                        break
                        # Last resort: use top-3 as-is
                        _ranked = _diversified if _diversified else _ranked[:3]
                        logger.info(
                            f"[auto_rebalancer] Diversify active (pool-level): "
                            f"pool_counts={_pool_counts} az_counts={_az_counts} "
                            f"→ selected {len(_ranked)} pool(s) after pool-uniqueness+AZ cap"
                        )
                    else:
                        _ranked = _ranked[:3]

                    # ── SIZE CAP: prevent upsizing during pure spot migration ────
                    # When NOT bin-packing, do not pick a pool whose instance type
                    # is larger than the current node (avoids paying more for
                    # a bigger instance just because it has lower risk).
                    # Allow up to 1.25x vCPU/memory headroom for equivalent tiers.
                    if not bin_packed:
                        _cur_specs_cap = _INSTANCE_VCPU_MEM.get(instance.instance_type)
                        if _cur_specs_cap:
                            _max_vcpu_cap = _cur_specs_cap[0] * 1.25
                            _max_mem_cap = _cur_specs_cap[1] * 1.25
                            _size_capped = [
                                _r for _r in _ranked
                                if (
                                    _INSTANCE_VCPU_MEM.get(_r.pool.instance_type, (0, 0))[0] <= _max_vcpu_cap
                                    and
                                    _INSTANCE_VCPU_MEM.get(_r.pool.instance_type, (0, 0))[1] <= _max_mem_cap
                                )
                            ]
                            if _size_capped:
                                logger.debug(
                                    f"[auto_rebalancer] Size cap: {len(_ranked)} → {len(_size_capped)} "
                                    f"pools (max {_max_vcpu_cap:.1f}vCPU/{_max_mem_cap:.1f}GB)"
                                )
                                _ranked = _size_capped

                    # ── DOUBLE GATE: 3-step selection hierarchy ──────────────────
                    # OD on-demand reference price for this instance type
                    _OD_PRICES_G = {
                        "t3.nano":0.0052,"t3.micro":0.0104,"t3.small":0.0208,
                        "t3.medium":0.0416,"t3.large":0.0832,"t3.xlarge":0.1664,
                        "t3.2xlarge":0.3328,"t3a.medium":0.0376,"t3a.large":0.0752,
                        "m5.large":0.096,"m5.xlarge":0.192,"m5.2xlarge":0.384,
                        "m6i.large":0.096,"m6i.xlarge":0.192,"c5.large":0.085,
                        "c5.xlarge":0.17,"c6i.large":0.085,"c6g.large":0.077,
                        "r5.large":0.126,"r5.xlarge":0.252,"m6g.large":0.077,
                    }
                    _od_price_g = _OD_PRICES_G.get(instance.instance_type, 0.10)
                    try:
                        from backend.models.cluster import OptimizationStrategy as _OS_g
                        _os_g = db.query(_OS_g).filter_by(cluster_id=cluster.id).first()
                        _tradeoff_g = (getattr(_os_g, 'risk_savings_tradeoff_pct', 20) or 20) / 100.0
                        _rceil_g = (getattr(_os_g, 'risk_ceiling_percent', 25) or 25) / 100.0
                    except Exception:
                        _tradeoff_g = 0.20
                        _rceil_g = 0.25
                    # Apply regional market factor to risk ceiling (clamped 0.8–1.2)
                    try:
                        _mf_raw_g = _redis.get(f"market_factor:{cluster.region or 'ap-south-1'}")
                        _rceil_g *= float(_mf_raw_g) if _mf_raw_g else 1.0
                    except Exception:
                        pass

                    _chosen_g = None
                    # Find cheapest valid spot price to calculate realistic tradeoff bounds
                    _valid_spots = [r for r in _ranked if r.pool.spot_price > 0]
                    _cheapest_spot = min(
                        _valid_spots, key=lambda x: x.pool.spot_price
                    ).pool.spot_price if _valid_spots else _od_price_g * 0.3

                    # Pass 1: cheaper (spot < OD price) AND risk below ceiling
                    for _rg in _ranked:
                        _cheaper_g = (
                            (_rg.pool.spot_price > 0 and _rg.pool.spot_price < _od_price_g) or
                            (_rg.pool.spot_price == 0 and _rg.predicted_savings > 0.05)
                        )
                        if _cheaper_g and _rg.risk_probability < _rceil_g:
                            _chosen_g = _rg
                            break
                            
                    # Pass 2 (tradeoff): allow giving up to tradeoff% of the OD savings
                    if not _chosen_g:
                        _max_g = _cheapest_spot + (_od_price_g - _cheapest_spot) * _tradeoff_g
                        _p2_g = [
                            _rg for _rg in _ranked
                            if ((_rg.pool.spot_price > 0 and _rg.pool.spot_price <= _max_g)
                                or _rg.pool.spot_price == 0)
                            and _rg.risk_probability < _rceil_g
                        ]
                        if _p2_g:
                            _chosen_g = min(_p2_g, key=lambda r: r.risk_probability)
                    # Risk override: node itself is dangerously risky → any safer pool, price ignored
                    if not _chosen_g:
                        _node_risk_g = float(instance.risk_score or 0.0)
                        if _node_risk_g > _rceil_g:
                            _safer_g = [_rg for _rg in _ranked if _rg.risk_probability < _node_risk_g]
                            if _safer_g:
                                _chosen_g = min(_safer_g, key=lambda r: r.risk_probability)

                    # OD→SPOT final fallback: any spot pool is still better than staying on OD.
                    # Spot is almost always cheaper than OD even at "high risk". Pick the
                    # lowest-risk pool that is at least cheaper than OD price.
                    if not _chosen_g and instance.lifecycle == InstanceLifecycle.ON_DEMAND:
                        _cheaper_any = [
                            r for r in _ranked
                            if r.pool.spot_price == 0 or r.pool.spot_price < _od_price_g
                        ]
                        if _cheaper_any:
                            _chosen_g = min(_cheaper_any, key=lambda r: r.risk_probability)
                            logger.info(
                                f"[auto_rebalancer] OD→SPOT fallback for {instance.instance_id}: "
                                f"using lowest-risk pool {_chosen_g.pool.instance_type}:{_chosen_g.pool.az} "
                                f"(risk={_chosen_g.risk_probability:.2f}, ceiling exceeded but still cheaper than OD)"
                            )
                        elif _ranked:
                            _chosen_g = _ranked[0]
                            logger.info(
                                f"[auto_rebalancer] OD→SPOT last-resort for {instance.instance_id}: "
                                f"using top-ranked pool {_ranked[0].pool.instance_type}:{_ranked[0].pool.az}"
                            )

                    if _chosen_g:
                        _p = _chosen_g.pool
                        target_pool = f"{_p.instance_type}:{_p.az}"
                        target_instance_type_final = _p.instance_type
                    else:
                        # No suitable spot pool found this cycle — leave OD node as-is
                        logger.debug(
                            f"[auto_rebalancer] No qualifying spot pool for {instance.instance_id} "
                            f"({instance.instance_type}, od_price={_od_price_g:.4f}, "
                            f"risk_ceil={_rceil_g:.2f}) — skipping this cycle"
                        )
                        target_pool = None  # sentinel: skip action creation
                except Exception:
                    target_instance_type_final = target_instance_type
                    # on exception: keep target_pool = source_pool as fallback

                if target_pool is None:
                    # No qualifying spot pool — create a deferred action so the UI
                    # can surface this as a visible event rather than a silent skip.
                    try:
                        _deferred_action = RebalancingAction(
                            cluster_id=cluster.id,
                            trigger='auto_rebalance',
                            source_pool=source_pool,
                            target_pool=source_pool,  # same as source — no better pool found; NOT NULL constraint requires a value
                            status='deferred',
                            started_at=datetime.utcnow(),
                            completed_at=datetime.utcnow(),
                            duration_seconds=0,
                            error_message=(
                                f"No compatible spot pool found for {instance.instance_type} "
                                f"(risk_ceil={_rceil_g:.0%}, tradeoff={_tradeoff_g:.0%}). "
                                f"Will retry next cycle."
                            ),
                            action_metadata={
                                'reason': 'no_pool_found',
                                'initiated_by': 'auto_rebalancer',
                                'instance_id': instance.instance_id,
                                'instance_type': instance.instance_type,
                                'risk_ceiling': round(_rceil_g, 3),
                                'tradeoff_pct': round(_tradeoff_g, 3),
                            },
                        )
                        db.add(_deferred_action)
                        db.commit()
                        logger.info(
                            f"[auto_rebalancer] Deferred action created for {instance.instance_id} "
                            f"— no qualifying spot pool (risk_ceil={_rceil_g:.0%})"
                        )
                    except Exception as _def_err:
                        logger.warning(f"[auto_rebalancer] Failed to create deferred action: {_def_err}")
                    continue  # try next OD instance

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
                        # AZs stored at creation so Decision Engine failure reporting
                        # and Phase-2 AZ fallback never rely on empty-string guards.
                        'target_az': target_pool.split(':')[1] if ':' in (target_pool or '') else (instance.az or ''),
                        'source_az': instance.az or '',
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
                                # TASK-1.1: termination_mode replaces decrement_asg boolean.
                                # stateful resize is a replacement-style operation — ASG DesiredCapacity stays.
                                "termination_mode": "replacement",
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
        if _redis:
            try:
                _redis.delete("lock:workers.auto_rebalancer")
            except Exception:
                pass
