"""
Standby Node Task — Launch and Maintain a Pre-Warmed Spare
===========================================================

Celery task that maintains a hot standby spot node in the cluster.
The standby is cordoned so no pods schedule on it, but it's ready
to be uncordoned instantly when a spot interruption occurs.

Lifecycle: provision → join K8s → cordon → mark standby=True → wait.
On activation: uncordon → mark standby=False → launch new standby.
"""

from datetime import datetime
from backend.core.logger import logger
from backend.workers.app import app


@app.task(name="launch_standby_node", bind=True, max_retries=2)
def launch_standby_node(self, cluster_id: str):
    """
    Launch a standby spot node for a cluster.

    Steps:
    1. Determine the maximum resource profile for the cluster.
    2. Call PoolRankingService for the best pool matching that profile.
    3. Launch a spot instance via CreateFleet.
    4. Wait for the node to become Ready in Kubernetes.
    5. Cordon the node via AgentAction.
    6. Mark it as standby=True in the Instance table.
    """
    from backend.models.base import get_db
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.core.redis_client import get_redis_client
    from backend.services.pool_ranking_service import PoolRankingService

    db = next(get_db())
    redis = get_redis_client()

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f"[standby] Cluster {cluster_id} not found")
            return {"status": "error", "message": "cluster_not_found"}

        # Check if standby already exists
        existing_standby = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.standby == True,
            Instance.state == "running",
        ).first()
        if existing_standby:
            logger.info(
                f"[standby] Cluster {cluster.name} already has standby "
                f"{existing_standby.node_name}"
            )
            return {"status": "already_exists", "node": existing_standby.node_name}

        # 1. Determine max resource profile
        region = cluster.region or "ap-south-1"
        running = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == "running",
        ).all()

        if not running:
            logger.warning(f"[standby] No running instances in cluster {cluster.name}")
            return {"status": "no_running_nodes"}

        svc = PoolRankingService(db, redis)
        catalog = svc.instance_catalog

        max_vcpu = 2
        max_memory = 4.0
        for inst in running:
            specs = catalog.get(inst.instance_type, {})
            max_vcpu = max(max_vcpu, specs.get("vcpu", 2))
            max_memory = max(max_memory, specs.get("memory_gb", 4.0))

        logger.info(
            f"[standby] Max profile for {cluster.name}: "
            f"{max_vcpu} vCPU / {max_memory} GB"
        )

        # 2. Get best pool from DE
        pools = svc.rank_pools_for_size(
            vcpu=max_vcpu,
            memory_gb=max_memory,
            region=region,
            limit=5,
        )

        if not pools:
            logger.error(f"[standby] No pools found for standby in {cluster.name}")
            return {"status": "no_pools"}

        best_pool = pools[0]
        logger.info(
            f"[standby] Selected {best_pool.pool.instance_type}:{best_pool.pool.az} "
            f"for standby (score={best_pool.ml_score:.3f})"
        )

        # 3. Launch spot instance (reuse existing Fleet launch logic)
        # For now, record the intent — actual launch uses the existing
        # auto_rebalancer Fleet launch machinery
        from backend.models.base import generate_uuid

        standby_action_id = generate_uuid()

        # Create a placeholder Instance record marking it as standby
        standby_instance = Instance(
            id=generate_uuid(),
            cluster_id=cluster_id,
            account_id=cluster.account_id,
            instance_type=best_pool.pool.instance_type,
            lifecycle="spot",
            az=best_pool.pool.az,
            state="provisioning",
            standby=True,
            node_name=f"standby-{cluster_id[:8]}",
        )
        db.add(standby_instance)
        db.commit()

        logger.info(
            f"[standby] Created standby instance record {standby_instance.id} "
            f"for cluster {cluster.name}"
        )

        # 5. Create CORDON AgentAction (will be picked up when node joins)
        cordon_action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.CORDON_NODE,
            payload={
                "node_name": standby_instance.node_name,
                "reason": "standby_cordoned",
            },
            status=AgentActionStatus.PENDING,
        )
        db.add(cordon_action)
        db.commit()

        logger.info(
            f"[standby] Standby launch initiated for {cluster.name}: "
            f"{best_pool.pool.instance_type} in {best_pool.pool.az}"
        )
        return {
            "status": "ok",
            "instance_id": standby_instance.id,
            "instance_type": best_pool.pool.instance_type,
            "az": best_pool.pool.az,
        }

    except Exception as e:
        logger.error(f"[standby] Failed for cluster {cluster_id}: {e}")
        db.rollback()
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


_ARM64_FAMILIES = {
    't4g', 'c6g', 'c7g', 'c8g', 'c8gn', 'm6g', 'm7g', 'm8g',
    'r6g', 'r7g', 'r8g', 'c6gn', 'c6gd', 'm6gd',
    'r6gd', 'a1', 'hpc7g',
}


def find_ready_standby(
    db,
    cluster_id: str,
    redis_client=None,
    source_instance_type: str = None,
    action_id: str = None,
):
    """
    Find and atomically claim a ready standby node for a cluster.

    When redis_client is provided this function:
      1. Queries the DB for a standby=True, state=running node.
      2. Checks the node is not already claimed by another action via
         Redis SET NX on ``spot:replacement_claimed:{instance_id}``.
      3. Verifies the standby architecture matches ``source_instance_type``
         (ARM64 vs x86).  If there is a mismatch the key is NOT claimed and
         None is returned.
      4. Performs the atomic Redis SET NX claim (TTL 3600 s).  If another
         caller wins the race, returns None.

    Returns the Instance record on success, None otherwise.
    """
    from backend.models.instance import Instance

    standby = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.standby == True,
        Instance.state == "running",
    ).first()

    if not standby:
        return None

    # Guard: node_name must be set — otherwise cordon/drain agent actions will fail
    if not standby.node_name:
        return None

    if redis_client is not None:
        _claim_key = f"spot:replacement_claimed:{standby.instance_id}"

        # Fast-exit: key already exists means another action already claimed this node
        try:
            if redis_client.exists(_claim_key):
                return None
        except Exception:
            pass

        # Architecture check — do NOT claim if arch mismatches source
        if source_instance_type and standby.instance_type:
            _src_fam = source_instance_type.split('.')[0]
            _sb_fam = standby.instance_type.split('.')[0]
            if (_src_fam in _ARM64_FAMILIES) != (_sb_fam in _ARM64_FAMILIES):
                return None

        # Atomic claim: only one caller wins the SET NX
        try:
            _claimed = redis_client.set(_claim_key, str(action_id or ''), nx=True, ex=3600)
            if not _claimed:
                # Another process claimed it between the exists() check and now
                return None
        except Exception:
            # Redis unavailable — skip standby rather than risk double-claim.
            # Log at WARNING so operators know standby was bypassed (not that none exists).
            try:
                from backend.core.logger import logger as _sb_logger
                _sb_logger.warning(
                    f"[find_ready_standby] Redis unavailable for cluster {cluster_id} — "
                    f"skipping standby claim to prevent double-claim (safe fallback to Phase 1)"
                )
            except Exception:
                pass
            return None

    return standby
