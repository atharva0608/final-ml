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
        logger.warning(
            f"[MOD-HEALTH-02] Cluster {cluster.name} agent offline "
            f"(last heartbeat: {cluster.last_heartbeat}). Resetting to DISCOVERED."
        )
        cluster.agent_installed = 'N'
        cluster.status = ClusterStatus.DISCOVERED

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
        logger.info(f"[MOD-HEALTH-02] Reset {len(stale)} stale agent(s) to DISCOVERED.")
