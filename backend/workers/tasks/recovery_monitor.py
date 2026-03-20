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
                        sts = boto3.client("sts", region_name=region, **base_creds)
                        assumed = sts.assume_role(
                            RoleArn=cluster.aws_role_arn,
                            RoleSessionName="spot-recovery-sync",
                            DurationSeconds=900,
                        )
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

        # ── Pass 1: platform-creds (same-account clusters) ────────────────────
        if base_key and base_secret:
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
                    )
                    assumed = sts.assume_role(
                        RoleArn=cluster.aws_role_arn,
                        RoleSessionName="spot-orphan-scan",
                        DurationSeconds=900,
                    )
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
    """Alias: runs both sync + scan + karpenter stall detection."""
    r1 = sync_instance_states.apply()
    r2 = scan_orphans.apply()
    r3 = detect_karpenter_stalls.apply()
    return {"sync": r1.result, "scan": r2.result, "karpenter_stalls": r3.result}

