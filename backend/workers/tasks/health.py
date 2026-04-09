import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from backend.core.config import settings
from backend.models.cluster import Cluster
from backend.models.instance import Instance

logger = logging.getLogger(__name__)

from backend.workers.app import app
from backend.models.base import get_db

@app.task(name="backend.workers.tasks.health.cleanup_zombie_nodes")
def cleanup_zombie_nodes_task():
    """
    Celery task to clean up zombie nodes.
    """
    try:
        db = next(get_db())
        cleanup_zombie_nodes(db)
    except Exception as e:
        logger.error(f"[MOD-HEALTH-01] Failed to cleanup zombie nodes: {e}")

@app.task(name="backend.workers.tasks.health.check_reversion_opportunities")
def check_reversion_opportunities_task():
    """
    Celery task to check for Spot reversion opportunities.
    """
    from backend.modules.spot_optimizer import get_spot_optimizer
    from backend.models.cluster import Cluster
    from backend.core.redis_client import get_redis_client
    
    try:
        db = next(get_db())
        clusters = db.query(Cluster).filter(Cluster.status == 'ACTIVE').all()
        
        redis_client = get_redis_client()
        optimizer = get_spot_optimizer(db, redis_client)
        
        for cluster in clusters:
            try:
                plans = optimizer.handle_fallback_reversion(cluster.id)
                if plans:
                    # In a real system, we'd execute these plans via Actuator
                    # For now, just log them
                    logger.info(f"[MOD-SPOT-04] Reversion opportunities for {cluster.name}: {plans}")
            except Exception as e:
                logger.error(f"[MOD-SPOT-04] Failed to check reversion for {cluster.name}: {e}")
                
    except Exception as e:
        logger.error(f"[MOD-SPOT-04] Failed to check reversion opportunities: {e}")

def cleanup_zombie_nodes(db: Session, threshold_minutes: int = 5):
    """
    MOD-HEALTH-01: Identify and cleanup zombie nodes.
    
    Logic:
    1. Query nodes with last_heartbeat < (Now - threshold)
    2. Check valid statuses (don't delete if intentionally stopped?)
    3. Mark as UNKNOWN/TERMINATED
    4. Sync with AWS (optional deep check, but for now just DB cleanup)
    """
    threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)
    
    zombies = db.query(Instance).filter(
        Instance.last_heartbeat < threshold_time,
        Instance.status != 'TERMINATED',
        Instance.status != 'UNKNOWN'
    ).all()
    
    if not zombies:
        logger.info("[MOD-HEALTH-01] No zombie nodes found.")
        return 0
        
    logger.info(f"[MOD-HEALTH-01] Found {len(zombies)} zombie nodes (last heartbeat < {threshold_minutes}m ago)")
    
    count = 0
    for node in zombies:
        # Check against AWS if possible? 
        # For now, just mark them so they don't pollute the dashboard
        # Ideally we should verify with Cluster State too
        
        previous_status = node.status
        node.status = 'UNKNOWN'
        node.status_message = f"Heartbeat lost since {node.last_heartbeat}. Marked as Zombie."
        logger.warning(f"Marking node {node.instance_id} as UNKNOWN (Prev: {previous_status}). Last active: {node.last_heartbeat}")
        count += 1
        
    db.commit()
    return count


@app.task(name="backend.workers.tasks.health.reset_stale_agents")
def reset_stale_agents_task():
    """
    Every minute: find clusters whose agent_installed='Y' but have had no
    heartbeat for >5 minutes (i.e. pods were manually deleted or crashed).
    Resets them to DISCOVERED state so the UI immediately reflects the real status.
    """
    try:
        db = next(get_db())
        _reset_stale_agents(db)
    except Exception as e:
        logger.error(f"[MOD-HEALTH-02] reset_stale_agents_task error: {e}")


def _reset_stale_agents(db: Session, stale_minutes: int = 5):
    from backend.models.cluster import ClusterStatus
    stale_threshold = datetime.utcnow() - timedelta(minutes=stale_minutes)

    stale = db.query(Cluster).filter(
        Cluster.agent_installed == 'Y',
        Cluster.last_heartbeat < stale_threshold,
    ).all()

    for cluster in stale:
        # ── K8s-based agent liveness fallback ────────────────────────────
        # Before marking DISCONNECTED, check if agent pods are actually Running
        # on the cluster via direct K8s API. The agent may be running fine but
        # can't reach this backend URL to send heartbeats (common when backend
        # is local/docker and agent is on remote EKS). If agent pods are healthy,
        # refresh the heartbeat timestamp and skip the DISCONNECTED path.
        try:
            from backend.services.karpenter_service import KarpenterService as _KS_hb
            from backend.core.redis_client import get_redis_client as _grc_hb
            _ks_hb = _KS_hb(db, _grc_hb())
            _api_client = _ks_hb._get_k8s_client(cluster)
            from kubernetes import client as _k8s_client
            _v1 = _k8s_client.CoreV1Api(_api_client)
            # Check for agent pods in spot-optimizer namespace
            _agent_pods = _v1.list_namespaced_pod(
                namespace="spot-optimizer",
                label_selector="app=spot-agent",
                timeout_seconds=10,
            )
            _running_agents = [
                p for p in _agent_pods.items
                if p.status and p.status.phase == 'Running'
            ]
            if _running_agents:
                # Agent pods are Running on K8s — refresh heartbeat, skip DISCONNECTED
                cluster.last_heartbeat = datetime.utcnow()
                cluster.status = ClusterStatus.ACTIVE
                logger.info(
                    f"[MOD-HEALTH-02] Cluster {cluster.name}: heartbeat stale but "
                    f"{len(_running_agents)} agent pod(s) Running on K8s — "
                    f"refreshed heartbeat via K8s liveness check"
                )
                # Also refresh Karpenter detection since agent can't do it
                try:
                    _det = _ks_hb.detect_karpenter_in_cluster(str(cluster.id), db)
                    if _det.get('detected'):
                        logger.info(
                            f"[MOD-HEALTH-02] Also refreshed Karpenter status for "
                            f"{cluster.name}: {_det.get('pods_running', 0)} pod(s) detected"
                        )
                except Exception:
                    pass
                continue  # skip DISCONNECTED path for this cluster
        except Exception as _k8s_hb_err:
            logger.debug(
                f"[MOD-HEALTH-02] K8s agent liveness check failed for "
                f"{cluster.name}: {_k8s_hb_err} — falling through to DISCONNECTED"
            )

        logger.warning(
            f"[MOD-HEALTH-02] Cluster {cluster.name} agent offline "
            f"(last heartbeat: {cluster.last_heartbeat}). Marking as DISCONNECTED."
        )
        # Keep agent_installed='Y' — the agent IS installed, just not sending
        # heartbeats. Setting it to 'N' causes the UI to show "Install Agent"
        # which is misleading. Use DISCONNECTED status to signal the issue.
        cluster.status = ClusterStatus.DISCONNECTED

        # Issue 5: Clear stale utilization data so ASCP auto-scaler doesn't act
        # on ghost metrics from a disconnected agent.
        try:
            from backend.models.instance import Instance
            _cleared = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running'
            ).update(
                {'cpu_util': None, 'memory_util': None},
                synchronize_session=False
            )
            if _cleared > 0:
                logger.info(
                    f"[MOD-HEALTH-02] Cleared utilization data for {_cleared} instance(s) "
                    f"in disconnected cluster {cluster.name}"
                )
        except Exception as _util_err:
            logger.warning(f"[MOD-HEALTH-02] Failed to clear utilization for {cluster.name}: {_util_err}")

        # BUG-9 fix: Cancel pending/picked-up AgentActions for this cluster.
        # Without this, actions stay in waiting_agent for up to 45 min, locking the cluster.
        try:
            from backend.models.agent_action import AgentAction
            from backend.models.rebalancing_action import RebalancingAction
            _pending_actions = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_(['PENDING', 'PICKED_UP'])
            ).all()
            for _pa in _pending_actions:
                _pa.status = 'CANCELLED'
                _pa.completed_at = datetime.utcnow()
                # Clear heartbeat key so rebalancer picks it up immediately
                try:
                    from backend.core.redis_client import get_redis_client as _grc_b9
                    _grc_b9().delete(f"action_heartbeat:{_pa.id}")
                except Exception:
                    pass

            _stuck_rebalances = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status.in_(['in_progress', 'waiting_agent'])
            ).all()
            for _sr in _stuck_rebalances:
                _sr.status = 'failed'
                _sr.error_message = 'AGENT_WENT_OFFLINE'
                _sr.completed_at = datetime.utcnow()
                # Full resource cleanup: Redis locks, semaphore, AND trigger pods.
                # Without this, trigger pods remain Pending in the cluster forever
                # and Redis locks block the node for up to 24h.
                try:
                    from backend.core.redis_client import get_redis_client as _grc_sr
                    from backend.workers.tasks.auto_rebalancer import _cleanup_rebalancing_resources
                    _sr_redis = _grc_sr()
                    _sr_meta = dict(_sr.action_metadata or {})
                    _cleanup_rebalancing_resources(
                        _sr, _sr_meta, _sr_redis, db,
                        decr_semaphore=True,
                    )
                except Exception:
                    pass

            if _pending_actions or _stuck_rebalances:
                logger.warning(
                    f"[MOD-HEALTH-02] Cluster {cluster.name} agent stale — "
                    f"cancelled {len(_pending_actions)} pending actions, "
                    f"failed {len(_stuck_rebalances)} stuck rebalances"
                )
        except Exception as _b9_err:
            logger.warning(f"[MOD-HEALTH-02] BUG-9 cleanup failed for {cluster.name}: {_b9_err}")

    if stale:
        db.commit()
        # Bust Redis cluster cache so API reflects the change immediately
        try:
            from backend.core.redis_client import get_redis_client
            r = get_redis_client()
            for key in r.scan_iter("clusters:*"):
                r.delete(key)
        except Exception:
            pass
        # Count how many were actually marked DISCONNECTED vs refreshed via K8s
        _actually_disconnected = [
            c for c in stale if c.status == ClusterStatus.DISCONNECTED
        ]
        _refreshed = len(stale) - len(_actually_disconnected)
        if _actually_disconnected:
            logger.info(f"[MOD-HEALTH-02] Marked {len(_actually_disconnected)} agent(s) as DISCONNECTED.")
        if _refreshed:
            logger.info(f"[MOD-HEALTH-02] Refreshed {_refreshed} agent(s) via K8s liveness check.")


# ── Z1 fix: Cleanup zombie OD instances ──────────────────────────────────────

@app.task(name="backend.workers.tasks.health.cleanup_zombie_od_instances")
def cleanup_zombie_od_instances_task():
    """
    Z1 fix: Find on-demand instances that are 'running' in the DB but have no
    K8s node (node_name is NULL) and are older than 10 minutes. These are zombies
    — EC2 is running but the node never joined or was removed from K8s.

    Uses DB + Redis only (no direct K8s API call). The node_name field is written
    by the agent heartbeat when the node joins the cluster. If it's NULL after
    10 minutes, the node never joined.

    Runs every hour via Celery beat.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.account import Account as AWSAccount
    from backend.models.system_config import SystemConfig
    from backend.core.redis_client import get_redis_client
    import boto3

    db = next(get_db())
    redis = get_redis_client()
    terminated_count = 0

    try:
        age_cutoff = datetime.utcnow() - timedelta(minutes=10)

        # Find OD instances: running, no node_name, older than 10 min, real EC2 ID
        zombie_candidates = db.query(Instance).filter(
            Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
            Instance.state == 'running',
            Instance.node_name.is_(None),
            Instance.created_at <= age_cutoff,
            Instance.instance_id.like('i-%'),
        ).all()

        if not zombie_candidates:
            return {"status": "ok", "terminated": 0}

        logger.info(
            f"[health/zombie-od] Found {len(zombie_candidates)} zombie OD candidate(s)"
        )

        for inst in zombie_candidates:
            try:
                # Skip if there's an active rebalancing action for this instance
                active_action = db.query(RebalancingAction).filter(
                    RebalancingAction.source_instance_id == inst.instance_id,
                    RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
                ).first()
                if active_action:
                    continue

                # Skip if there's an active node_action key in Redis
                if redis.exists(f"spot:node_active_action:{inst.instance_id}"):
                    continue

                # Get cluster and credentials to terminate
                cluster = db.query(Cluster).filter(Cluster.id == inst.cluster_id).first()
                if not cluster:
                    continue

                # Get platform credentials
                pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
                ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
                if not pk or not ps or not pk.value or not ps.value:
                    continue

                region = cluster.region or 'ap-south-1'

                # Use assumed role for cross-account clusters
                ec2 = None
                if cluster.aws_role_arn:
                    try:
                        sts = boto3.client(
                            "sts", region_name=region,
                            aws_access_key_id=pk.value,
                            aws_secret_access_key=ps.value,
                        )
                        _assume_kwargs = {
                            "RoleArn": cluster.aws_role_arn,
                            "RoleSessionName": "spot-zombie-od-cleanup",
                            "DurationSeconds": 900,
                        }
                        if getattr(cluster, 'aws_external_id', None):
                            _assume_kwargs["ExternalId"] = cluster.aws_external_id
                        assumed = sts.assume_role(**_assume_kwargs)
                        c = assumed["Credentials"]
                        ec2 = boto3.client(
                            "ec2", region_name=region,
                            aws_access_key_id=c["AccessKeyId"],
                            aws_secret_access_key=c["SecretAccessKey"],
                            aws_session_token=c["SessionToken"],
                        )
                    except Exception as _role_err:
                        logger.debug(
                            f"[health/zombie-od] assume_role failed for {cluster.name}: {_role_err}"
                        )
                        continue
                else:
                    ec2 = boto3.client(
                        "ec2", region_name=region,
                        aws_access_key_id=pk.value,
                        aws_secret_access_key=ps.value,
                    )

                # Verify instance is still running in AWS before terminating
                try:
                    resp = ec2.describe_instances(InstanceIds=[inst.instance_id])
                    aws_state = None
                    for res in resp.get("Reservations", []):
                        for i in res.get("Instances", []):
                            aws_state = i["State"]["Name"]
                    if aws_state != "running":
                        # Already terminated/stopping — just update DB
                        inst.state = "terminated"
                        inst.terminated_at = datetime.utcnow()
                        db.commit()
                        terminated_count += 1
                        continue
                except Exception as _desc_err:
                    logger.debug(f"[health/zombie-od] describe failed for {inst.instance_id}: {_desc_err}")
                    continue

                # Terminate the zombie
                ec2.terminate_instances(InstanceIds=[inst.instance_id])
                inst.state = "terminated"
                inst.terminated_at = datetime.utcnow()
                db.commit()
                terminated_count += 1
                logger.warning(
                    f"[health/zombie-od] Terminated zombie OD instance {inst.instance_id} "
                    f"(no K8s node, age {(datetime.utcnow() - inst.created_at).total_seconds() / 60:.1f} min, "
                    f"cluster {inst.cluster_id})"
                )

            except Exception as inst_err:
                logger.error(f"[health/zombie-od] Error processing {inst.instance_id}: {inst_err}")
                db.rollback()

        if terminated_count:
            logger.warning(
                f"[health/zombie-od] Terminated {terminated_count} zombie OD instance(s)"
            )

        return {"status": "ok", "terminated": terminated_count}

    except Exception as e:
        logger.error(f"[health/zombie-od] Fatal: {e}")
        return {"status": "error", "error": str(e)}


# ── Z5 fix: Periodic cluster_pools sync ──────────────────────────────────────

@app.task(name="backend.workers.tasks.health.sync_cluster_pools")
def sync_cluster_pools_task():
    """
    Z5 fix: Rebuild the cluster_pools:{cluster_id} Redis set from actual DB state.

    The set tracks which instance_type:az pools are in use by each cluster's
    running spot instances. Stale entries can accumulate when emergency launches
    fail or instances are terminated outside the normal flow.

    Rebuilds the set every 30 minutes by querying running/pending SPOT instances
    from the DB and replacing the Redis set with the current state.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.core.redis_client import get_redis_client

    db = next(get_db())
    redis = get_redis_client()
    synced = 0

    try:
        clusters = db.query(Cluster).filter(Cluster.status == 'active').all()

        for cluster in clusters:
            try:
                # Get actual running/pending SPOT instances
                live_pools = set()
                spot_instances = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state.in_(['running', 'pending']),
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                ).all()
                for inst in spot_instances:
                    if inst.instance_type and inst.az:
                        live_pools.add(f"{inst.instance_type}:{inst.az}")

                # Z5 race guard: exclude pools with a recent dry_run failure.
                # When a pool is srem'd after a launch failure, sync might re-add it
                # before the dry_run fail cache (60s) expires. Use dry_run cache as proxy.
                _filtered_pools = set()
                for _pool in live_pools:
                    _parts = _pool.split(":", 1)
                    if len(_parts) == 2:
                        _dr_key = f"dry_run:{_parts[0]}:{_parts[1]}"
                        try:
                            _dr_val = redis.get(_dr_key)
                            if _dr_val and (_dr_val.decode() if isinstance(_dr_val, bytes) else _dr_val) == "fail":
                                continue  # skip — recently failed, srem was correct
                        except Exception:
                            pass
                    _filtered_pools.add(_pool)

                pool_key = f"cluster_pools:{cluster.id}"
                # Atomic replace: delete + sadd in pipeline
                pipe = redis.pipeline()
                pipe.delete(pool_key)
                if _filtered_pools:
                    pipe.sadd(pool_key, *_filtered_pools)
                pipe.execute()
                synced += 1
            except Exception as cluster_err:
                logger.debug(f"[health/cluster-pools-sync] Failed for {cluster.id}: {cluster_err}")

        if synced:
            logger.info(f"[health/cluster-pools-sync] Synced cluster_pools for {synced} cluster(s)")

        return {"status": "ok", "synced": synced}

    except Exception as e:
        logger.error(f"[health/cluster-pools-sync] Fatal: {e}")
        return {"status": "error", "error": str(e)}
