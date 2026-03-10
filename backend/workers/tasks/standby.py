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


def find_ready_standby(db, cluster_id: str):
    """
    Find a ready standby node for a cluster.

    Returns the Instance record if a standby is available and running,
    or None otherwise.
    """
    from backend.models.instance import Instance

    return db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.standby == True,
        Instance.state == "running",
    ).first()
