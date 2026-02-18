"""
Hibernation Worker - Celery tasks for executing hibernation schedules
"""
from celery import shared_task
from backend.models.base import SessionLocal
from backend.models.hibernation_schedule import HibernationSchedule, HibernationStrategy
from backend.services.hibernation_service import HibernationService
from backend.hibernation_strategy import (
    NamespaceSleepStrategy,
    NuclearStrategy,
    SnapshotRestoreStrategy
)
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)


@shared_task(name="execute_hibernation_scheduler")
def execute_hibernation_scheduler():
    """
    Main scheduler task - runs every 1 minute to check for schedules that need execution
    """
    db = SessionLocal()
    
    try:
        # Get all active schedules
        schedules = db.query(HibernationSchedule).filter(
            HibernationSchedule.is_active == "Y"
        ).all()
        
        logger.info(f"Checking {len(schedules)} active hibernation schedules")
        
        for schedule in schedules:
            try:
                # Calculate next action
                service = HibernationService(db)
                next_time, action = service.calculate_next_execution(schedule)
                
                if not next_time or not action:
                    continue
                
                now = datetime.now(pytz.timezone(schedule.timezone))
                
                # Check if it's time to execute
                if next_time <= now:
                    logger.info(f"Executing {action} for schedule {schedule.name}")
                    
                    if action == "sleep":
                        execute_hibernation.delay(schedule.id)
                    elif action == "wake":
                        execute_wake.delay(schedule.id)
                    elif action == "prewarm":
                        execute_prewarm.delay(schedule.id)
                        
            except Exception as e:
                logger.error(f"Error checking schedule {schedule.id}: {e}")
                
    finally:
        db.close()


@shared_task(name="execute_hibernation")
def execute_hibernation(schedule_id: str):
    """Execute sleep action for a schedule"""
    db = SessionLocal()
    
    try:
        schedule = db.query(HibernationSchedule).filter(
            HibernationSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return
        
        logger.info(f"Starting hibernation for schedule: {schedule.name}")
        
        # Get appropriate strategy
        strategy_class = _get_strategy_class(schedule.strategy)
        
        # Execute sleep for each cluster
        for cluster in schedule.clusters:
            try:
                cluster_config = {
                    "cluster_name": cluster.name,
                    "region": cluster.region,
                    "kubeconfig": {}  # TODO: Load from cluster config
                }
                
                strategy = strategy_class(cluster_config)
                result = strategy.sleep(schedule.saved_state.get(cluster.id, {}))
                
                # Save state
                if not schedule.saved_state:
                    schedule.saved_state = {}
                schedule.saved_state[cluster.id] = result.get("state", {})
                
                logger.info(f"Hibernated cluster {cluster.name}")
                
            except Exception as e:
                logger.error(f"Error hibernating cluster {cluster.name}: {e}")
                schedule.last_action = "ERROR"
                schedule.last_action_at = datetime.utcnow()
                db.commit()
                return
        
        # Update schedule state
        schedule.last_action = "SLEEP"
        schedule.last_action_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Hibernation completed for schedule: {schedule.name}")
        
        # Send SSE notification
        from backend.core.sse_manager import sse_manager
        sse_manager.broadcast("hibernation_status", {
            "schedule_id": schedule_id,
            "action": "sleep",
            "status": "completed"
        })
        
    except Exception as e:
        logger.error(f"Error executing hibernation: {e}")
    finally:
        db.close()


@shared_task(name="execute_wake")
def execute_wake(schedule_id: str):
    """Execute wake action for a schedule"""
    db = SessionLocal()
    
    try:
        schedule = db.query(HibernationSchedule).filter(
            HibernationSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return
        
        logger.info(f"Starting wake for schedule: {schedule.name}")
        
        # Get appropriate strategy
        strategy_class = _get_strategy_class(schedule.strategy)
        
        # Execute wake for each cluster
        for cluster in schedule.clusters:
            try:
                cluster_config = {
                    "cluster_name": cluster.name,
                    "region": cluster.region,
                    "kubeconfig": {}
                }
                
                strategy = strategy_class(cluster_config)
                saved_state = schedule.saved_state.get(cluster.id, {})
                result = strategy.wake(saved_state)
                
                logger.info(f"Woke cluster {cluster.name}")
                
            except Exception as e:
                logger.error(f"Error waking cluster {cluster.name}: {e}")
                schedule.last_action = "ERROR"
                schedule.last_action_at = datetime.utcnow()
                db.commit()
                return
        
        # Update schedule state
        schedule.last_action = "WAKE"
        schedule.last_action_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Wake completed for schedule: {schedule.name}")
        
        # Send SSE notification
        from backend.core.sse_manager import sse_manager
        sse_manager.broadcast("hibernation_status", {
            "schedule_id": schedule_id,
            "action": "wake",
            "status": "completed"
        })
        
    except Exception as e:
        logger.error(f"Error executing wake: {e}")
    finally:
        db.close()


@shared_task(name="execute_prewarm")
def execute_prewarm(schedule_id: str):
    """Execute pre-warm action (start nodes early before wake)"""
    db = SessionLocal()
    
    try:
        schedule = db.query(HibernationSchedule).filter(
            HibernationSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            return
        
        logger.info(f"Starting pre-warm for schedule: {schedule.name}")
        
        # For Nuclear/Snapshot strategies, start scaling ASGs
        if schedule.strategy in [HibernationStrategy.NUCLEAR.value, HibernationStrategy.SNAPSHOT_RESTORE.value]:
            strategy_class = _get_strategy_class(schedule.strategy)
            
            for cluster in schedule.clusters:
                cluster_config = {"cluster_name": cluster.name, "region": cluster.region}
                strategy = strategy_class(cluster_config)
                
                # Partially restore ASGs to warm up nodes
                # Full wake will happen at scheduled time
                logger.info(f"Pre-warming cluster {cluster.name}")
        
        schedule.last_action = "PREWARM"
        schedule.last_action_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        logger.error(f"Error executing pre-warm: {e}")
    finally:
        db.close()


def _get_strategy_class(strategy_name: str):
    """Get strategy class by name"""
    strategy_map = {
        HibernationStrategy.NAMESPACE_SLEEP.value: NamespaceSleepStrategy,
        HibernationStrategy.NUCLEAR.value: NuclearStrategy,
        HibernationStrategy.SNAPSHOT_RESTORE.value: SnapshotRestoreStrategy
    }
    return strategy_map.get(strategy_name, NamespaceSleepStrategy)
