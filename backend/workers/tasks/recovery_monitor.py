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

                # Try assumed role first; fall back to platform creds
                import boto3
                try:
                    sts = boto3.client("sts", region_name=region, **base_creds)
                    if cluster.role_arn:
                        assumed = sts.assume_role(
                            RoleArn=cluster.role_arn,
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
                    else:
                        ec2 = boto3.client("ec2", region_name=region, **base_creds)
                except Exception:
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
                                    if iid not in aws_states:
                                        aws_states[iid] = "terminated"  # Not returned = terminated
                                except Exception:
                                    aws_states[iid] = "terminated"  # Not found individually
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
    """
    from backend.models.base import get_db
    from backend.models.system_config import SystemConfig
    from backend.core.redis_client import get_redis_client
    from backend.core.config import ORPHAN_INSTANCE_TIMEOUT_MIN
    import boto3
    from datetime import datetime, timezone

    db = next(get_db())
    redis = get_redis_client()

    try:
        pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        pr = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()

        if not pk or not ps or not pk.value or not ps.value:
            return {"status": "ok", "orphans_terminated": 0, "skipped": "no_credentials"}

        region = pr.value if (pr and pr.value) else "ap-south-1"
        ec2 = boto3.client(
            "ec2", region_name=region,
            aws_access_key_id=pk.value,
            aws_secret_access_key=ps.value,
        )

        response = ec2.describe_instances(
            Filters=[
                {"Name": "tag:spot-optimizer:status", "Values": ["pending"]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )

        now = datetime.now(timezone.utc)
        timeout_secs = ORPHAN_INSTANCE_TIMEOUT_MIN * 60
        orphans_terminated = 0

        for reservation in response.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                iid = inst["InstanceId"]
                launch_time = inst.get("LaunchTime")
                if not launch_time:
                    continue

                age_secs = (now - launch_time).total_seconds()
                if age_secs < timeout_secs:
                    continue

                # Skip if the node successfully joined K8s
                if redis.exists(f"node_joined:{iid}"):
                    continue

                try:
                    ec2.terminate_instances(InstanceIds=[iid])
                    orphans_terminated += 1
                    logger.warning(
                        f"[scan_orphans] Terminated orphan {iid} "
                        f"(age={age_secs:.0f}s, no node_joined key)"
                    )
                except Exception as term_err:
                    logger.error(f"[scan_orphans] Failed to terminate {iid}: {term_err}")

        return {"status": "ok", "orphans_terminated": orphans_terminated}

    except Exception as e:
        logger.error(f"[scan_orphans] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# Legacy task name alias (for backward compat with existing beat schedule)
@app.task(name="recovery_monitor", bind=True, max_retries=1)
def recovery_monitor(self):
    """Alias: runs both sync + scan."""
    r1 = sync_instance_states.apply()
    r2 = scan_orphans.apply()
    return {"sync": r1.result, "scan": r2.result}
