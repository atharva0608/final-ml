"""
Recovery Monitor — Sync AWS Instance States & Detect Orphans
=============================================================

Two Celery tasks:

1. `sync_instance_states` (every 5 min):
   For each active cluster, call EC2 DescribeInstances and mark
   any instance that AWS says is terminated/shutting-down as
   state='terminated' in the DB. This prevents stale "running"
   records from accumulating in the UI.

2. `scan_orphans` (every 5 min):
   Detect EC2 instances tagged spot-optimizer:status=pending
   that are > ORPHAN_INSTANCE_TIMEOUT_MIN old and have no
   node_joined:{iid} Redis key. Terminate them and log.

Per changes.md §9.
"""

from backend.core.logger import logger
from backend.workers.app import app


# ── Task 1: Sync AWS instance states to DB ────────────────────────────────────

@app.task(name="backend.workers.tasks.recovery_monitor.sync_instance_states",
          bind=True, max_retries=1)
def sync_instance_states(self):
    """
    For each active cluster, describe all known EC2 instance IDs and
    update state='terminated' in DB for any that AWS marks terminated/shutting-down.
    Runs every 5 minutes via Celery beat.
    """
    from backend.models.base import get_db
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.models.instance import Instance
    from backend.models.system_config import SystemConfig
    from datetime import datetime

    db = next(get_db())
    total_synced = 0

    try:
        # Get platform credentials for direct EC2 calls
        pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        if not pk or not ps or not pk.value or not ps.value:
            logger.debug("[recovery/sync] No platform credentials — skipping state sync")
            return {"status": "ok", "synced": 0, "skipped": "no_credentials"}

        base_creds = {
            "aws_access_key_id": pk.value,
            "aws_secret_access_key": ps.value,
        }

        clusters = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).all()

        for cluster in clusters:
            try:
                # Instances recorded as 'running' in DB
                db_running = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()
                if not db_running:
                    continue

                instance_ids = [
                    i.instance_id for i in db_running
                    if i.instance_id and i.instance_id.startswith('i-')
                ]
                if not instance_ids:
                    continue

                region = cluster.region or "ap-south-1"

                # Use assumed role for cross-account clusters; skip if assume fails
                # (falling back to platform creds would describe a different account
                # and return empty results, causing all instances to look "terminated")
                import boto3
                ec2 = None
                if cluster.aws_role_arn:
                    try:
                        sts = boto3.client("sts", region_name=region, **base_creds,
                                           endpoint_url=f"https://sts.{region}.amazonaws.com")
                        _assume_kwargs_sync = {
                            "RoleArn": cluster.aws_role_arn,
                            "RoleSessionName": "spot-recovery-sync",
                            "DurationSeconds": 900,
                        }
                        if getattr(cluster, 'aws_external_id', None):
                            _assume_kwargs_sync["ExternalId"] = cluster.aws_external_id
                        assumed = sts.assume_role(**_assume_kwargs_sync)
                        c = assumed["Credentials"]
                        ec2 = boto3.client(
                            "ec2", region_name=region,
                            aws_access_key_id=c["AccessKeyId"],
                            aws_secret_access_key=c["SecretAccessKey"],
                            aws_session_token=c["SessionToken"],
                        )
                    except Exception as _role_err:
                        logger.debug(
                            f"[recovery/sync] Skipping cluster {cluster.name}: "
                            f"assume_role failed ({_role_err})"
                        )
                        continue  # Skip cross-account cluster — don't fall back to platform creds
                else:
                    ec2 = boto3.client("ec2", region_name=region, **base_creds)

                # Batch describe (max 1000 IDs per call)
                BATCH = 200
                aws_states = {}
                for i in range(0, len(instance_ids), BATCH):
                    batch_ids = instance_ids[i:i + BATCH]
                    try:
                        resp = ec2.describe_instances(InstanceIds=batch_ids)
                        for res in resp.get("Reservations", []):
                            for inst in res.get("Instances", []):
                                aws_states[inst["InstanceId"]] = inst["State"]["Name"]
                    except Exception as e:
                        if "InvalidInstanceID" in str(e):
                            # One or more IDs not found — re-query individually to identify which
                            for iid in batch_ids:
                                if iid in aws_states:
                                    continue
                                try:
                                    r2 = ec2.describe_instances(InstanceIds=[iid])
                                    for res2 in r2.get("Reservations", []):
                                        for inst2 in res2.get("Instances", []):
                                            aws_states[inst2["InstanceId"]] = inst2["State"]["Name"]
                                    # NOTE: if iid not in response, leave aws_states[iid] unset.
                                    # "Not returned" ≠ "terminated" — it may mean permission gap.
                                except Exception as _ind_err:
                                    logger.debug(
                                        f"[recovery/sync] Single-id describe failed "
                                        f"for {iid}: {_ind_err} — leaving state unchanged"
                                    )
                                    # Do NOT mark terminated — can't confirm state
                        else:
                            logger.warning(f"[recovery/sync] DescribeInstances failed for {cluster.name}: {e}")

                # Update DB records whose AWS state is now terminal
                TERMINAL = {"terminated", "shutting-down"}
                for inst in db_running:
                    if not inst.instance_id:
                        continue
                    aws_state = aws_states.get(inst.instance_id)
                    if aws_state in TERMINAL:
                        inst.state = "terminated"
                        inst.updated_at = datetime.utcnow()
                        total_synced += 1
                        logger.info(
                            f"[recovery/sync] Marked {inst.instance_id} "
                            f"({inst.instance_type}) as terminated in cluster {cluster.name}"
                        )
                    elif aws_state == "running" and inst.state != "running":
                        inst.state = "running"
                        inst.updated_at = datetime.utcnow()

                db.commit()

            except Exception as cluster_err:
                logger.warning(f"[recovery/sync] Failed for cluster {cluster.name}: {cluster_err}")
                db.rollback()

        return {"status": "ok", "synced": total_synced}

    except Exception as e:
        logger.error(f"[recovery/sync] Fatal: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# ── Task 2: Scan orphaned "pending" instances ─────────────────────────────────

@app.task(name="backend.workers.tasks.recovery_monitor.scan_orphans",
          bind=True, max_retries=1)
def scan_orphans(self):
    """
    Detect EC2 instances tagged spot-optimizer:status=pending that were
    launched > ORPHAN_INSTANCE_TIMEOUT_MIN minutes ago and have no
    node_joined:{instance_id} Redis key. Terminate them.

    Runs TWO passes:
    1. Platform-creds pass — covers instances in the platform's own AWS account.
    2. Per-cluster assumed-role pass — covers cross-account customer clusters
       (instances launched by the rebalancer via role assumption).
    """
    from backend.models.base import get_db
    from backend.models.system_config import SystemConfig
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.core.redis_client import get_redis_client
    from backend.core.config import ORPHAN_INSTANCE_TIMEOUT_MIN
    import boto3
    from datetime import datetime, timezone

    db = next(get_db())
    redis = get_redis_client()
    orphans_terminated = 0
    now = datetime.now(timezone.utc)
    timeout_secs = ORPHAN_INSTANCE_TIMEOUT_MIN * 60

    ORPHAN_FILTERS = [
        {"Name": "tag:spot-optimizer:status", "Values": ["pending"]},
        {"Name": "instance-state-name", "Values": ["running"]},
    ]

    def _check_and_terminate(ec2_client, reservations):
        """Shared inner loop: check age + node_joined key, terminate if orphan."""
        count = 0
        for reservation in reservations:
            for inst in reservation.get("Instances", []):
                iid = inst["InstanceId"]
                launch_time = inst.get("LaunchTime")
                if not launch_time:
                    continue
                age_secs = (now - launch_time).total_seconds()
                if age_secs < timeout_secs:
                    continue
                if redis.exists(f"node_joined:{iid}"):
                    continue
                # Problem #18: Double-check before termination — look for node_name
                # in DB (from agent heartbeat) and check for manual override key
                _skip_terminate = False
                try:
                    # Check manual override
                    if redis.exists(f"spot:prevent_orphan_termination:{iid}"):
                        logger.info(f"[scan_orphans] Skipping {iid} — manual override key set")
                        _skip_terminate = True
                    if not _skip_terminate:
                        from backend.models.instance import Instance as _InstOrph
                        _db_inst = db.query(_InstOrph).filter(
                            _InstOrph.instance_id == iid[:20]
                        ).first()
                        if _db_inst and _db_inst.node_name:
                            # Agent has reported a node_name — instance has joined K8s
                            logger.info(
                                f"[scan_orphans] Skipping {iid} — has node_name={_db_inst.node_name} "
                                f"in DB (agent heartbeat confirmed join)"
                            )
                            _skip_terminate = True
                        elif _db_inst and hasattr(_db_inst, 'last_heartbeat') and _db_inst.last_heartbeat:
                            # Check if agent heartbeat is recent (< 5 min)
                            _hb_age = (now - _db_inst.last_heartbeat).total_seconds() if _db_inst.last_heartbeat else 99999
                            if _hb_age < 300:
                                logger.info(
                                    f"[scan_orphans] Skipping {iid} — recent agent heartbeat "
                                    f"({_hb_age:.0f}s ago)"
                                )
                                _skip_terminate = True
                except Exception as _p18_err:
                    logger.debug(f"[scan_orphans] Double-check failed for {iid}: {_p18_err}")
                if _skip_terminate:
                    continue
                try:
                    ec2_client.terminate_instances(InstanceIds=[iid])
                    count += 1
                    logger.warning(
                        f"[scan_orphans] Terminated orphan {iid} "
                        f"(age={age_secs:.0f}s, no node_joined key)"
                    )
                except Exception as term_err:
                    logger.error(f"[scan_orphans] Failed to terminate {iid}: {term_err}")
        return count

    try:
        pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        pr = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()

        base_key = pk.value if pk else None
        base_secret = ps.value if ps else None
        default_region = pr.value if (pr and pr.value) else "ap-south-1"

        # ── Pass 1: platform-creds (same-account clusters only) ──────────────
        # P-M5 fix: only run Pass 1 if there are same-account clusters (no aws_role_arn).
        # For all-cross-account deployments, Pass 1 scans the wrong account and always
        # returns 0 results — wasting API quota every 5 min.
        _same_account_exists = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE,
            Cluster.aws_role_arn.is_(None),
        ).count() > 0
        if base_key and base_secret and _same_account_exists:
            try:
                ec2_plat = boto3.client(
                    "ec2", region_name=default_region,
                    aws_access_key_id=base_key,
                    aws_secret_access_key=base_secret,
                )
                resp = ec2_plat.describe_instances(Filters=ORPHAN_FILTERS)
                orphans_terminated += _check_and_terminate(ec2_plat, resp.get("Reservations", []))
            except Exception as e:
                logger.warning(f"[scan_orphans] Platform-creds pass failed: {e}")

        # ── Pass 2: per-cluster assumed-role (cross-account clusters) ─────────
        if base_key and base_secret:
            clusters = db.query(Cluster).filter(
                Cluster.status == ClusterStatus.ACTIVE,
                Cluster.aws_role_arn.isnot(None),
            ).all()
            for cluster in clusters:
                try:
                    region = cluster.region or default_region
                    sts = boto3.client(
                        "sts", region_name=region,
                        aws_access_key_id=base_key,
                        aws_secret_access_key=base_secret,
                        endpoint_url=f"https://sts.{region}.amazonaws.com",
                    )
                    _assume_kwargs_orphan = {
                        "RoleArn": cluster.aws_role_arn,
                        "RoleSessionName": "spot-orphan-scan",
                        "DurationSeconds": 900,
                    }
                    if getattr(cluster, 'aws_external_id', None):
                        _assume_kwargs_orphan["ExternalId"] = cluster.aws_external_id
                    assumed = sts.assume_role(**_assume_kwargs_orphan)
                    c = assumed["Credentials"]
                    ec2_assumed = boto3.client(
                        "ec2", region_name=region,
                        aws_access_key_id=c["AccessKeyId"],
                        aws_secret_access_key=c["SecretAccessKey"],
                        aws_session_token=c["SessionToken"],
                    )
                    resp2 = ec2_assumed.describe_instances(Filters=ORPHAN_FILTERS)
                    orphans_terminated += _check_and_terminate(
                        ec2_assumed, resp2.get("Reservations", [])
                    )
                except Exception as cluster_err:
                    logger.debug(
                        f"[scan_orphans] Assumed-role pass failed for {cluster.name}: {cluster_err}"
                    )

        return {"status": "ok", "orphans_terminated": orphans_terminated}

    except Exception as e:
        logger.error(f"[scan_orphans] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# ── Task 3: Karpenter consolidation stall detection (Task 3.7) ────────────────

@app.task(name="backend.workers.tasks.recovery_monitor.detect_karpenter_stalls",
          bind=True, max_retries=1)
def detect_karpenter_stalls(self):
    """
    Detect Karpenter-mode terminate actions that dispatched >15 min ago
    but whose target instance is still running in AWS.

    Karpenter's consolidation controller can stall if the NodeClaim
    reconciler loses track of a node (e.g. after a control-plane restart).
    In that case, the TERMINATE_NODE action completed on our side but
    the EC2 instance is still alive.

    Fix: Direct ec2.terminate_instances() as fallback.
    Runs every 5 minutes via Celery beat.
    """
    from backend.models.base import get_db
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.models.system_config import SystemConfig
    from datetime import datetime, timedelta
    import boto3
    import json

    db = next(get_db())
    stalls_fixed = 0

    try:
        # Find TERMINATE_NODE actions with mode=karpenter completed >15 min ago
        cutoff = datetime.utcnow() - timedelta(minutes=15)

        karpenter_terminates = db.query(AgentAction).filter(
            AgentAction.action_type == AgentActionType.TERMINATE_NODE,
            AgentAction.status == AgentActionStatus.COMPLETED,
            AgentAction.completed_at <= cutoff,
            AgentAction.completed_at >= datetime.utcnow() - timedelta(hours=2),  # Only last 2h
        ).all()

        if not karpenter_terminates:
            return {"status": "ok", "stalls_fixed": 0}

        # Filter to karpenter-mode only
        karpenter_actions = []
        for act in karpenter_terminates:
            payload = act.payload or {}
            if payload.get("termination_mode") == "karpenter":
                karpenter_actions.append(act)

        if not karpenter_actions:
            return {"status": "ok", "stalls_fixed": 0}

        logger.info(
            f"[recovery/karpenter-stall] Checking {len(karpenter_actions)} "
            f"karpenter terminate actions for stalls"
        )

        # Get platform credentials
        pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        if not pk or not ps or not pk.value or not ps.value:
            return {"status": "ok", "stalls_fixed": 0, "skipped": "no_credentials"}

        for act in karpenter_actions:
            payload = act.payload or {}
            instance_id = payload.get("instance_id")
            if not instance_id or not instance_id.startswith("i-"):
                continue

            cluster = db.query(Cluster).filter(Cluster.id == act.cluster_id).first()
            if not cluster:
                continue

            try:
                region = cluster.region or "ap-south-1"
                # P-C4 fix: use assumed-role credentials for cross-account clusters.
                # Platform credentials cannot describe instances in customer accounts.
                ec2 = None
                if cluster.aws_role_arn:
                    try:
                        sts = boto3.client(
                            "sts", region_name=region,
                            aws_access_key_id=pk.value,
                            aws_secret_access_key=ps.value,
                            endpoint_url=f"https://sts.{region}.amazonaws.com",
                        )
                        _assume_kwargs_karp = {
                            "RoleArn": cluster.aws_role_arn,
                            "RoleSessionName": "spot-karpenter-stall",
                            "DurationSeconds": 900,
                        }
                        if getattr(cluster, 'aws_external_id', None):
                            _assume_kwargs_karp["ExternalId"] = cluster.aws_external_id
                        assumed = sts.assume_role(**_assume_kwargs_karp)
                        c = assumed["Credentials"]
                        ec2 = boto3.client(
                            "ec2", region_name=region,
                            aws_access_key_id=c["AccessKeyId"],
                            aws_secret_access_key=c["SecretAccessKey"],
                            aws_session_token=c["SessionToken"],
                        )
                    except Exception as _assume_err:
                        logger.warning(
                            f"[recovery/karpenter-stall] assume_role failed for cluster "
                            f"{cluster.name} ({_assume_err}) — skipping stall check"
                        )
                        continue
                else:
                    ec2 = boto3.client(
                        "ec2", region_name=region,
                        aws_access_key_id=pk.value,
                        aws_secret_access_key=ps.value,
                    )

                # Check if instance is still running
                resp = ec2.describe_instances(InstanceIds=[instance_id])
                for res in resp.get("Reservations", []):
                    for inst in res.get("Instances", []):
                        state = inst["State"]["Name"]
                        if state == "running":
                            # Stall detected — force terminate
                            logger.warning(
                                f"[recovery/karpenter-stall] Instance {instance_id} still "
                                f"running {(datetime.utcnow() - act.completed_at).total_seconds() / 60:.0f}min "
                                f"after karpenter terminate action — force terminating"
                            )
                            ec2.terminate_instances(InstanceIds=[instance_id])
                            stalls_fixed += 1

                            # Update action metadata to record the force-terminate
                            meta = act.action_metadata or {}
                            meta["karpenter_stall_detected"] = True
                            meta["force_terminated_at"] = datetime.utcnow().isoformat()
                            act.action_metadata = meta
                            db.commit()

            except Exception as inst_err:
                logger.debug(
                    f"[recovery/karpenter-stall] Check failed for {instance_id}: {inst_err}"
                )

        if stalls_fixed:
            logger.warning(
                f"[recovery/karpenter-stall] Force-terminated {stalls_fixed} stalled instance(s)"
            )

        return {"status": "ok", "stalls_fixed": stalls_fixed}

    except Exception as e:
        logger.error(f"[recovery/karpenter-stall] Fatal: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# Legacy task name alias (for backward compat with existing beat schedule)
@app.task(name="recovery_monitor", bind=True, max_retries=1)
def recovery_monitor(self):
    """Alias: runs both sync + scan + karpenter stall detection + stuck cordon recovery."""

    def _safe_result(task_result, name: str):
        """BUG-15 fix: isolate each subtask — one failure doesn't crash the umbrella."""
        try:
            return {"status": "ok", "result": task_result.result}
        except Exception as e:
            logger.error("recovery_monitor subtask %s failed: %s", name, e)
            return {"status": "error", "error": str(e)}

    r1 = sync_instance_states.apply()
    r2 = scan_orphans.apply()
    r3 = detect_karpenter_stalls.apply()
    r4 = recover_stuck_cordoned_nodes.apply()
    return {
        "sync": _safe_result(r1, "sync_instance_states"),
        "scan": _safe_result(r2, "scan_orphans"),
        "karpenter_stalls": _safe_result(r3, "detect_karpenter_stalls"),
        "stuck_cordons": _safe_result(r4, "recover_stuck_cordoned_nodes"),
    }


# ── Task 3b: Recover stuck cordoned nodes (Z2 fix) ───────────────────────────

@app.task(name="backend.workers.tasks.recovery_monitor.recover_stuck_cordoned_nodes",
          bind=True, max_retries=1)
def recover_stuck_cordoned_nodes(self):
    """
    Z2 fix: Detect nodes that were cordoned by the rebalancer but whose
    RebalancingAction subsequently failed without a successful uncordon.

    The backend does not have direct K8s API access, so we rely on DB state:
    1. Find failed RebalancingActions where cordon was applied (step_2_cordon
       timestamp exists in action_metadata).
    2. Check that no pending UNCORDON_NODE AgentAction already exists for that node.
    3. Check the cluster agent is online (last_heartbeat < 5 min).
    4. Dispatch a new UNCORDON_NODE AgentAction.

    Also catches in_progress/waiting_agent actions stuck for > 20 min past
    cordon completion — indicates a stall that may have left the node cordoned.

    Runs every 5 minutes via the recovery_monitor umbrella task.
    """
    from backend.models.base import get_db
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.agent_action import (
        AgentAction, AgentActionType, AgentActionStatus,
    )
    from backend.models.cluster import Cluster
    from backend.core.redis_client import get_redis_client
    from datetime import datetime, timedelta

    db = next(get_db())
    redis = get_redis_client()
    uncordons_queued = 0

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=20)

        # ── 1. Failed actions where cordon was applied ─────────────────────
        failed_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status == 'failed',
            RebalancingAction.completed_at >= datetime.utcnow() - timedelta(hours=2),
        ).all()

        # ── 2. Stuck waiting_agent/in_progress actions past cordon ─────────
        stuck_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status.in_(['waiting_agent', 'in_progress']),
            RebalancingAction.started_at <= cutoff,
        ).all()

        candidates = []
        for action in failed_actions + stuck_actions:
            meta = action.action_metadata or {}
            # Only act on actions where cordon was successfully completed
            if 'step_2_cordon' not in meta:
                continue
            node_name = meta.get('target_node_name') or meta.get('node_name')
            if not node_name:
                continue
            candidates.append((action, node_name))

        if not candidates:
            return {"status": "ok", "uncordons_queued": 0}

        for action, node_name in candidates:
            try:
                # Check cluster agent is online
                cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
                if not cluster or not cluster.last_heartbeat:
                    continue
                hb_age = (datetime.utcnow() - cluster.last_heartbeat).total_seconds()
                if hb_age > 300:  # Agent offline > 5 min — skip
                    continue

                # Check no pending/picked_up UNCORDON already exists for this node
                existing_uncordon = db.query(AgentAction).filter(
                    AgentAction.cluster_id == action.cluster_id,
                    AgentAction.action_type == AgentActionType.UNCORDON_NODE,
                    AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                    AgentAction.payload.contains({"node_name": node_name}),
                ).count()
                if existing_uncordon > 0:
                    continue

                # Also skip if uncordon was recently completed (< 10 min ago)
                recent_uncordon = db.query(AgentAction).filter(
                    AgentAction.cluster_id == action.cluster_id,
                    AgentAction.action_type == AgentActionType.UNCORDON_NODE,
                    AgentAction.status == AgentActionStatus.COMPLETED,
                    AgentAction.payload.contains({"node_name": node_name}),
                    AgentAction.completed_at >= datetime.utcnow() - timedelta(minutes=10),
                ).count()
                if recent_uncordon > 0:
                    continue

                # Dispatch UNCORDON_NODE
                uncordon_action = AgentAction(
                    cluster_id=action.cluster_id,
                    action_type=AgentActionType.UNCORDON_NODE,
                    status=AgentActionStatus.PENDING,
                    payload={"node_name": node_name},
                    action_metadata={
                        "recovery_reason": "Z2_stuck_cordon",
                        "original_action_id": str(action.id),
                    },
                )
                db.add(uncordon_action)
                db.commit()
                uncordons_queued += 1
                logger.warning(
                    f"[recovery/stuck-cordon] Queued UNCORDON_NODE for {node_name} "
                    f"(failed action {action.id}, cluster {action.cluster_id})"
                )

            except Exception as node_err:
                logger.debug(
                    f"[recovery/stuck-cordon] Error processing action {action.id}: {node_err}"
                )
                db.rollback()

        if uncordons_queued:
            logger.warning(
                f"[recovery/stuck-cordon] Queued {uncordons_queued} UNCORDON_NODE action(s)"
            )

        return {"status": "ok", "uncordons_queued": uncordons_queued}

    except Exception as e:
        logger.error(f"[recovery/stuck-cordon] Fatal: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# ── Task 4: Cluster coverage computation (Fix 13 from changes.md) ────────────

@app.task(name="backend.workers.tasks.recovery_monitor.compute_all_cluster_coverage",
          bind=True, max_retries=1)
def compute_all_cluster_coverage(self):
    """
    Compute spot pool coverage for all active clusters and cache in Redis.

    Key: cluster_coverage:{cluster_id}  (JSON, TTL 300s)

    Coverage status per node:
      COVERED    — ≥3 capacity-verified pools available
      AT_RISK    — 1-2 capacity-verified pools available
      STRANDED   — 0 capacity-verified pools available
      STATEFUL   — node has stateful workloads, spot not applicable
      UNCLASSIFIED — WorkloadInspector hasn't classified this node yet

    Runs every 5 minutes via Celery beat.
    """
    from backend.models.base import get_db
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.models.instance import Instance
    from backend.core.redis_client import get_redis_client
    from datetime import datetime
    import json

    db = next(get_db())
    redis = get_redis_client()
    results = {}

    try:
        clusters = db.query(Cluster).filter(Cluster.status == ClusterStatus.ACTIVE).all()

        for cluster in clusters:
            try:
                nodes = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()

                if not nodes:
                    continue

                coverage = {}
                verified_key = f"verified_pools:{cluster.id}"
                alt_count = redis.zcard(verified_key) or 0

                # Get best pool from verified set
                best_raw = redis.zrevrange(verified_key, 0, 0, withscores=True)
                best_pool_key = None
                if best_raw:
                    pk = best_raw[0][0]
                    best_pool_key = pk.decode() if isinstance(pk, bytes) else pk

                for node in nodes:
                    # Check workload classification
                    classification = None
                    try:
                        raw_cls = redis.get(f"workload_classification:{node.instance_id}")
                        if raw_cls:
                            cls_data = json.loads(raw_cls)
                            classification = cls_data.get("classification")
                    except Exception:
                        pass

                    if classification in ("STATEFUL", "STATEFUL_PROTECTED"):
                        coverage[node.instance_id] = {
                            "status": "STATEFUL",
                            "alternative_count": 0,
                            "best_option": None,
                            "saving_pct": 0,
                            "node_type": node.instance_type,
                        }
                        continue

                    if classification is None:
                        coverage[node.instance_id] = {
                            "status": "UNCLASSIFIED",
                            "alternative_count": alt_count,
                            "best_option": best_pool_key,
                            "saving_pct": 0,
                            "node_type": node.instance_type,
                        }
                        continue

                    if alt_count >= 3:
                        status = "COVERED"
                    elif alt_count >= 1:
                        status = "AT_RISK"
                    else:
                        status = "STRANDED"

                    coverage[node.instance_id] = {
                        "status": status,
                        "alternative_count": alt_count,
                        "best_option": best_pool_key,
                        "saving_pct": 0,
                        "node_type": node.instance_type,
                        "az": node.az,
                        "lifecycle": node.lifecycle,
                    }

                total_nodes = len(nodes)
                stateful_count = sum(1 for v in coverage.values() if v["status"] == "STATEFUL")
                rebalanceable = total_nodes - stateful_count
                covered = sum(1 for v in coverage.values() if v["status"] == "COVERED")
                at_risk = sum(1 for v in coverage.values() if v["status"] == "AT_RISK")
                stranded = sum(1 for v in coverage.values() if v["status"] == "STRANDED")

                coverage_pct = round(covered / rebalanceable * 100, 1) if rebalanceable > 0 else 0.0

                result = {
                    "cluster_id": cluster.id,
                    "total_nodes": total_nodes,
                    "covered": covered,
                    "at_risk": at_risk,
                    "stranded": stranded,
                    "stateful": stateful_count,
                    "coverage_pct": coverage_pct,
                    "per_node": coverage,
                    "computed_at": datetime.utcnow().isoformat(),
                }

                redis.setex(f"cluster_coverage:{cluster.id}", 360, json.dumps(result))  # Issue 3d: was 300s — must exceed beat period
                results[cluster.id] = {"coverage_pct": coverage_pct, "covered": covered, "total": total_nodes}

                if stranded > 0:
                    logger.warning(
                        f"[cluster_coverage] Cluster {cluster.name}: "
                        f"{stranded} STRANDED node(s) — no verified pools available"
                    )

            except Exception as cluster_err:
                logger.warning(f"[cluster_coverage] Failed for cluster {cluster.name}: {cluster_err}")

        logger.info(f"[cluster_coverage] Computed coverage for {len(results)} clusters")
        return {"status": "ok", "clusters": len(results), "results": results}

    except Exception as e:
        logger.error(f"[cluster_coverage] Fatal: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()

