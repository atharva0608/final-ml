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
