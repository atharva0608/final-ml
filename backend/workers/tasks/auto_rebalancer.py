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

        if not aws_lifecycle_map:
            logger.warning(f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                           f"(check tag kubernetes.io/cluster/{cluster.name} on EC2 instances)")
            return

        # Build set of instance_ids already in DB for this cluster
        db_instances = db.query(Instance).filter(Instance.cluster_id == cluster.id).all()
        db_id_map = {inst.instance_id: inst for inst in db_instances}

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

        # Sync cluster-level spot/od counters to match AWS reality
        cluster.spot_count = spot_count
        cluster.on_demand_node_count = od_count
        db.commit()

        logger.warning(
            f"[aws_sync] Cluster {cluster.name}: {spot_count} SPOT, {od_count} ON_DEMAND "
            f"({corrected} updated, {created} created from AWS truth, {len(aws_lifecycle_map)} instances found)"
        )

    except ClientError as e:
        logger.warning(f"[aws_sync] AWS API error syncing cluster {cluster.name}: {e}")
    except Exception as e:
        logger.warning(f"[aws_sync] Sync failed for cluster {cluster.name}: {e}")


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

                    # ── PRE-STEP: Reduce ASG desired capacity ──────────────────────────
                    # Before draining the node, tell the ASG to NOT replace it.
                    # Without this, the ASG immediately launches a new on-demand node after
                    # TERMINATE, so Karpenter never sees PENDING pods and never provisions spot.
                    # We use the backend's assumed IAM role (full permissions) for this call.
                    _asg_reduced = False
                    _asg_name_used = None
                    if instance_id_for_action and instance_id_for_action.startswith('i-'):
                        try:
                            import boto3 as _b3_asg
                            from botocore.exceptions import ClientError as _CE
                            # Resolve role ARN: cluster-level → account-level → no assumption
                            _role_arn = cluster.aws_role_arn
                            _ext_id   = cluster.aws_external_id
                            _region   = cluster.region or "ap-south-1"
                            if not _role_arn and cluster.account_id:
                                try:
                                    from backend.models.account import Account as _AcctASG
                                    _a = db.query(_AcctASG).filter(_AcctASG.id == cluster.account_id).first()
                                    if _a:
                                        _role_arn = _a.role_arn
                                        _ext_id   = _a.external_id
                                except Exception:
                                    pass
                            _asg_creds = {}
                            if _role_arn:
                                _sts = _b3_asg.client("sts")
                                _assume_kw = {"RoleArn": _role_arn,
                                              "RoleSessionName": "spot-rebalancer-asg-decrement"}
                                if _ext_id:
                                    _assume_kw["ExternalId"] = _ext_id
                                _assumed = _sts.assume_role(**_assume_kw)
                                _c = _assumed["Credentials"]
                                _asg_creds = {
                                    "aws_access_key_id":     _c["AccessKeyId"],
                                    "aws_secret_access_key": _c["SecretAccessKey"],
                                    "aws_session_token":     _c["SessionToken"],
                                }
                            _asg_client = _b3_asg.client("autoscaling", region_name=_region, **_asg_creds)
                            # Look up which ASG this instance belongs to
                            _asg_resp = _asg_client.describe_auto_scaling_instances(
                                InstanceIds=[instance_id_for_action]
                            )
                            if _asg_resp.get("AutoScalingInstances"):
                                _asg_inst = _asg_resp["AutoScalingInstances"][0]
                                _asg_name = _asg_inst["AutoScalingGroupName"]
                                _asg_info = _asg_client.describe_auto_scaling_groups(
                                    AutoScalingGroupNames=[_asg_name]
                                )
                                if _asg_info.get("AutoScalingGroups"):
                                    _grp = _asg_info["AutoScalingGroups"][0]
                                    _cur_desired  = _grp["DesiredCapacity"]
                                    _cur_min      = _grp["MinSize"]
                                    _new_desired  = max(_cur_min, _cur_desired - 1)
                                    if _new_desired < _cur_desired:
                                        _asg_client.update_auto_scaling_group(
                                            AutoScalingGroupName=_asg_name,
                                            DesiredCapacity=_new_desired,
                                        )
                                        _asg_reduced  = True
                                        _asg_name_used = _asg_name
                                        logger.info(
                                            f"[auto_rebalancer] Reduced ASG '{_asg_name}' desired "
                                            f"{_cur_desired}→{_new_desired} so Karpenter can provision spot"
                                        )
                                    else:
                                        logger.info(
                                            f"[auto_rebalancer] ASG '{_asg_name}' already at min "
                                            f"({_cur_min}) — not reducing further"
                                        )
                            else:
                                logger.info(
                                    f"[auto_rebalancer] Instance {instance_id_for_action} not in any ASG "
                                    f"(may be Karpenter-managed) — skipping ASG decrement"
                                )
                        except Exception as _asg_err:
                            logger.warning(
                                f"[auto_rebalancer] Could not reduce ASG desired for "
                                f"{instance_id_for_action}: {_asg_err} — continuing anyway"
                            )

                    # ── ZERO-DOWNTIME ORDERING ─────────────────────────────────────────
                    # Step 1: PATCH_KARPENTER_NODEPOOL first — tells Karpenter to provision
                    #         a new spot node BEFORE we cordon the old one.
                    #         When Karpenter is off, this action is a no-op but queued for
                    #         traceability. The agent handles it gracefully (Karpenter CRDs absent).
                    #
                    # Step 2: CORDON — prevent new pods scheduling on old node
                    #
                    # Step 3: DRAIN — evict pods with proper graceful shutdown.
                    #         Pods reschedule to the new spot node (if Karpenter provisioned it)
                    #         or remaining nodes. grace_period=60s gives pods more time to migrate.
                    #
                    # Step 4: TERMINATE — old node is empty; terminate via boto3 (Celery worker).
                    #
                    # This mirrors the Karpenter best-practice disruption order:
                    # provision → cordon → drain → delete (not: cordon → drain → terminate → provision)

                    # Use ML-ranked top spot pools for NodePool update.
                    # EC2NodeClass now uses AL2023 amiFamily with alias: al2023@latest —
                    # this supports BOTH amd64 (x86_64) AND arm64 (Graviton) automatically.
                    # Karpenter selects the correct AMI per architecture at provisioning time.
                    # So we no longer filter out ARM64 instance types — Graviton pools are
                    # 20% cheaper and fully supported.
                    ml_instance_types = [target_instance_type] if target_instance_type else ["t3.medium"]

                    # Determine required architectures from WorkloadInspector cache (Bug A-5)
                    # If workloads on this node are pinned to amd64, only offer amd64 pools.
                    # Otherwise allow both — EC2NodeClass (AL2023) handles arch-specific AMIs.
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
                                _arch_values = _node_archs  # respect workload pinning
                    except Exception:
                        pass  # fall back to allowing both

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
                        pass  # Keep fallback to target_instance_type

                    nodepool_action = AgentAction(
                        cluster_id=action.cluster_id,
                        action_type=AgentActionType.PATCH_KARPENTER_NODEPOOL,
                        payload={
                            "nodepool_name": "default",
                            "instance_types": ml_instance_types,
                            "capacity_type": ["spot"],
                            "az": target_az,
                            "architecture": _arch_values,  # both amd64+arm64 unless workload pinned
                            "rebalancing_action_id": action.id,
                            "zero_downtime_step": 1,  # First step: request spot provisioning
                        }
                    )
                    cordon_action = AgentAction(
                        cluster_id=action.cluster_id,
                        action_type=AgentActionType.CORDON_NODE,
                        payload={
                            "instance_id": instance_id_for_action,
                            "instance_type": source_instance_type,
                            "az": source_az,
                            "rebalancing_action_id": action.id,
                            "zero_downtime_step": 2,  # Second step: after spot provisioned
                        }
                    )
                    drain_action = AgentAction(
                        cluster_id=action.cluster_id,
                        action_type=AgentActionType.DRAIN_NODE,
                        payload={
                            "instance_id": instance_id_for_action,
                            "instance_type": source_instance_type,
                            "az": source_az,
                            "ignore_daemonsets": True,
                            "grace_period_seconds": 60,  # 60s grace for proper pod migration
                            "rebalancing_action_id": action.id,
                            "zero_downtime_step": 3,  # Third step: pods migrate to spot node
                        }
                    )
                    # Step 4: TERMINATE_NODE via agent (after drain completes).
                    # CRITICAL: Do NOT terminate here in the Celery worker — that causes
                    # Karpenter to see Pending pods and provision using the OLD NodePool
                    # config (before PATCH_NODEPOOL runs). The agent executes actions
                    # sequentially, so PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE ensures
                    # the NodePool is patched with ML types BEFORE Karpenter provisions.
                    terminate_action = AgentAction(
                        cluster_id=action.cluster_id,
                        action_type=AgentActionType.TERMINATE_NODE,
                        payload={
                            "instance_id": instance_id_for_action,
                            "node_name": None,
                            "rebalancing_action_id": action.id,
                            "zero_downtime_step": 4,  # Final: delete node after drain
                            # decrement_asg=True: reduces ASG desired capacity so ASG won't
                            # relaunch a replacement on-demand node — Karpenter provisions spot
                            "decrement_asg": True,
                        }
                    )

                    # Queue all 4 in order: PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE
                    # The agent executes these sequentially in creation order
                    db.add(nodepool_action)
                    db.add(cordon_action)
                    db.add(drain_action)
                    db.add(terminate_action)
                    db.flush()

                    logger.info(
                        f"[auto_rebalancer] Queued 4 AgentActions for cluster {cluster.id}: "
                        f"PATCH_NODEPOOL(spot:{ml_instance_types[:3]}) → "
                        f"CORDON → DRAIN → TERMINATE {source_instance_type}:{source_az}"
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
                    continue  # Agent still working — leave as waiting_agent

                _failed = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                    _AA0.status == _AAS0.FAILED
                ).count()
                # ── Backend EC2 terminate: drain is done, now kill the instance ──
                # Agent's kubectl delete node removes the K8s object but leaves EC2
                # running. We must terminate via backend's assumed IAM role to ensure
                # the instance is actually gone so Karpenter provisions a spot replacement.
                _wa_meta = _wa.action_metadata or {}
                _wa_instance_id = _wa_meta.get("instance_id", "")
                if _wa_instance_id and _wa_instance_id.startswith("i-") and _failed == 0:
                    try:
                        import boto3 as _b3wa
                        _wa_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
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
                        if _wa_role_arn:
                            _sts_wa = _b3wa.client("sts")
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
                        _asg_wa = _b3wa.client("autoscaling",
                                               region_name=_wa_cluster.region or "ap-south-1",
                                               **_wa_creds)
                        _asg_wa.terminate_instance_in_auto_scaling_group(
                            InstanceId=_wa_instance_id,
                            ShouldDecrementDesiredCapacity=True
                        )
                        logger.info(
                            f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                            f"via ASG (action {_wa.id} post-drain)"
                        )
                    except Exception as _term_err:
                        logger.warning(
                            f"[auto_rebalancer] Backend EC2 terminate failed for "
                            f"{_wa_instance_id}: {_term_err} (K8s node already removed)"
                        )

                _wa.status = 'failed' if _failed > 0 else 'completed'
                _wa.completed_at = datetime.utcnow()
                _wa.duration_seconds = (
                    int((_wa.completed_at - _wa.started_at).total_seconds())
                    if _wa.started_at else 0
                )
                if _failed > 0:
                    _wa.error_message = f"{_failed} agent action(s) failed"
                logger.info(
                    f"[auto_rebalancer] Action {_wa.id} resolved to {_wa.status} "
                    f"(all AgentActions done)"
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
        from backend.models.instance import Instance
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
                # Update NodePool with current ML-ranked spot pools (30-min cooldown)
                _nodepool_cooldown_key = f"spot:karpenter:nodepool_updated:{cluster.id}"
                try:
                    if _redis and not _redis.exists(_nodepool_cooldown_key):
                        from backend.models.instance import Instance as _Inst
                        _od_inst = db.query(_Inst).filter(
                            _Inst.cluster_id == cluster.id,
                            _Inst.lifecycle == InstanceLifecycle.ON_DEMAND
                        ).first()
                        if _od_inst:
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            from backend.models.agent_action import AgentAction as _AA, AgentActionType as _AAT
                            _specs = _INSTANCE_VCPU_MEM.get(_od_inst.instance_type, (2, 8))
                            _ranked = PoolRankingService(db, _redis).rank_pools_for_size(
                                vcpu=_specs[0], memory_gb=float(_specs[1]),
                                region=cluster.region or "ap-south-1", limit=5
                            )
                            if _ranked:
                                _ml_types = list(dict.fromkeys(
                                    [p.pool.instance_type for p in _ranked]
                                ))[:5]
                                _np_action = _AA(
                                    cluster_id=cluster.id,
                                    action_type=_AAT.PATCH_KARPENTER_NODEPOOL,
                                    payload={
                                        "nodepool_name": "default",
                                        "instance_types": _ml_types,
                                        "capacity_type": ["spot"],
                                        "reason": "ml_pool_refresh",
                                    }
                                )
                                db.add(_np_action)
                                db.commit()
                                if _redis:
                                    _redis.setex(_nodepool_cooldown_key, 1800, "1")  # 30-min cooldown
                                logger.info(
                                    f"[auto_rebalancer] Karpenter cluster {cluster.name}: "
                                    f"Updated NodePool with ML-ranked spot pools: {_ml_types}"
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
            # Auto-expire stale PICKED_UP actions (> 15 min) — these are orphaned by
            # agent restarts and would block the rebalancer indefinitely otherwise.
            from backend.models.agent_action import AgentAction, AgentActionStatus
            _expire_cutoff = datetime.utcnow() - timedelta(minutes=15)
            stale_count = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status == AgentActionStatus.PICKED_UP,
                AgentAction.created_at < _expire_cutoff,
            ).update({"status": AgentActionStatus.EXPIRED}, synchronize_session=False)
            if stale_count:
                db.flush()
                logger.warning(
                    f"[auto_rebalancer] Expired {stale_count} stale PICKED_UP AgentAction(s) "
                    f"for cluster {cluster.name} (>15 min old — agent restart likely)"
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
            # Never drain the final remaining on-demand node — doing so leaves the cluster
            # with no worker nodes and Karpenter deadlocked (it can't schedule itself).
            # Always keep at least 1 on-demand node alive as the cluster foundation.
            _total_nodes = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running',
            ).count()
            _od_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',
            ).count()
            if _total_nodes <= 1 or _od_count <= 1:
                logger.info(
                    f"[auto_rebalancer] Cluster {cluster.name}: only {_total_nodes} total / "
                    f"{_od_count} on-demand node(s) — refusing to drain the last node"
                )
                continue

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
                _COOLDOWN = 1200  # 20-minute cooldown (was 10 min — 10 min wasn't enough for Karpenter)
                if elapsed < _COOLDOWN:
                    # Check if a spot node appeared (Karpenter provisioned it successfully)
                    _spot_appeared = db.query(Instance).filter(
                        Instance.cluster_id == cluster.id,
                        Instance.lifecycle == InstanceLifecycle.SPOT,
                        Instance.state == 'running',
                    ).count() > 0
                    if not _spot_appeared:
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: cooldown "
                            f"({int(_COOLDOWN - elapsed)}s remaining, no spot node yet) — "
                            f"waiting for Karpenter to provision before draining next node"
                        )
                        continue
                    else:
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: spot node appeared — "
                            f"proceeding with next rebalancing cycle"
                        )

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
            on_demand_instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND
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
