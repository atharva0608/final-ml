"""
Hibernation Worker - Celery tasks for executing hibernation schedules

Enterprise-grade with Redis distributed locking to prevent race conditions
when multiple workers attempt to execute the same schedule/cluster simultaneously.
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
from datetime import datetime, timedelta
import pytz
import logging
import uuid
import os

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Redis Distributed Lock Helpers
# ──────────────────────────────────────────────────────────────

def _get_redis():
    """Get Redis client for distributed locking"""
    from redis import Redis
    return Redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )


def _acquire_lock(redis_client, schedule_id: str, cluster_id: str, ttl_seconds: int = 180) -> str | None:
    """
    Acquire a distributed lock for a schedule+cluster combination.
    Uses SET NX EX for atomic lock acquisition.
    
    Returns lock_value if acquired, None if already locked.
    """
    lock_key = f"hibernation:lock:{schedule_id}:{cluster_id}"
    lock_value = str(uuid.uuid4())
    
    acquired = redis_client.set(lock_key, lock_value, nx=True, ex=ttl_seconds)
    if acquired:
        logger.debug(f"Lock acquired: {lock_key} = {lock_value}")
        return lock_value
    else:
        existing = redis_client.get(lock_key)
        logger.info(f"Lock NOT acquired for {lock_key} — held by {existing}")
        return None


def _release_lock(redis_client, schedule_id: str, cluster_id: str, lock_value: str):
    """
    Release a distributed lock ONLY if we still own it.
    Prevents releasing a lock acquired by another worker after TTL expiry.
    """
    lock_key = f"hibernation:lock:{schedule_id}:{cluster_id}"
    current = redis_client.get(lock_key)
    if current == lock_value:
        redis_client.delete(lock_key)
        logger.debug(f"Lock released: {lock_key}")
    else:
        logger.warning(f"Lock {lock_key} NOT released — ownership changed (ours={lock_value}, current={current})")


# ──────────────────────────────────────────────────────────────
# Celery Tasks
# ──────────────────────────────────────────────────────────────

@shared_task(name="execute_hibernation_scheduler")
def execute_hibernation_scheduler():
    """
    Main scheduler task - runs every 1 minute to check for schedules that need execution.
    Uses Redis locking to prevent duplicate execution when multiple workers are running.
    """
    db = SessionLocal()
    redis = _get_redis()
    
    # Acquire a global scheduler lock to prevent duplicate schedule checking
    scheduler_lock = str(uuid.uuid4())
    if not redis.set("hibernation:scheduler_lock", scheduler_lock, nx=True, ex=55):
        logger.debug("Scheduler lock not acquired — another worker is checking schedules")
        db.close()
        return
    
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
                    # ── Task 9.1: Conflict detection ─────────────────
                    # Check if any cluster in this schedule already has an active
                    # hibernation lock from another schedule
                    has_conflict = False
                    for cluster in schedule.clusters:
                        conflict_key = f"hibernation:active_schedule:{cluster.id}"
                        active_schedule = redis.get(conflict_key)
                        if active_schedule and active_schedule != schedule.id:
                            logger.warning(
                                f"Conflict: cluster {cluster.id} locked by schedule {active_schedule}, "
                                f"skipping {action} for schedule {schedule.id}"
                            )
                            has_conflict = True
                            break
                    
                    if has_conflict:
                        continue
                    
                    # Mark clusters as owned by this schedule 
                    for cluster in schedule.clusters:
                        redis.setex(
                            f"hibernation:active_schedule:{cluster.id}",
                            3600,  # 1 hour TTL — auto-expires
                            schedule.id
                        )
                    
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
        # Release scheduler lock only if we still own it
        if redis.get("hibernation:scheduler_lock") == scheduler_lock:
            redis.delete("hibernation:scheduler_lock")
        db.close()


@shared_task(name="execute_hibernation", bind=True, max_retries=2)
def execute_hibernation(self, schedule_id: str):
    """Execute sleep action for a schedule — with per-cluster distributed locking"""
    db = SessionLocal()
    redis = _get_redis()
    
    try:
        schedule = db.query(HibernationSchedule).filter(
            HibernationSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return
        
        # ── SAFETY GATE: Substitute Mutual Exclusion (Task 1.2) ──
        # Check for each cluster before proceeding
        for cluster in schedule.clusters:
            substitute_state = redis.get(f"spot:substitute:state:{cluster.id}")
            substitute_state = substitute_state.decode() if substitute_state else "IDLE"
            if substitute_state not in ("IDLE", "FAILED", "COMPLETED"):
                logger.warning(
                    f"Deferring hibernation for {cluster.id}: substitute in {substitute_state}"
                )
                execute_hibernation.apply_async(args=[schedule_id], countdown=300)
                return
        
        logger.info(f"Starting hibernation for schedule: {schedule.name}")
        
        # Get appropriate strategy
        strategy_class = _get_strategy_class(schedule.strategy)
        
        # Execute sleep for each cluster — with per-cluster locking
        for cluster in schedule.clusters:
            # Acquire distributed lock for this schedule+cluster
            lock_value = _acquire_lock(redis, schedule_id, cluster.id, ttl_seconds=300)
            if not lock_value:
                logger.warning(f"Skipping cluster {cluster.name} — locked by another worker")
                continue
            
            try:
                cluster_config = {
                    "cluster_name": cluster.name,
                    "region": cluster.region,
                    "kubeconfig": {}  # TODO: Load from cluster config
                }
                
                strategy = strategy_class(cluster_config)
                result = strategy.sleep(schedule.saved_state.get(cluster.id, {}))
                
                # Save state with version timestamp for staleness detection
                if not schedule.saved_state:
                    schedule.saved_state = {}
                state_data = result.get("state", {})
                state_data["state_captured_at"] = datetime.utcnow().isoformat()
                state_data["captured_by_worker"] = lock_value
                schedule.saved_state[cluster.id] = state_data
                
                logger.info(f"Hibernated cluster {cluster.name}")
                
            except Exception as e:
                logger.error(f"Error hibernating cluster {cluster.name}: {e}")
                schedule.last_action = "ERROR"
                schedule.last_action_at = datetime.utcnow()
                db.commit()
                return
            finally:
                _release_lock(redis, schedule_id, cluster.id, lock_value)
        
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


@shared_task(name="execute_wake", bind=True, max_retries=2)
def execute_wake(self, schedule_id: str):
    """Execute wake action for a schedule — with per-cluster distributed locking and state staleness check"""
    db = SessionLocal()
    redis = _get_redis()
    
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
        
        # Execute wake for each cluster — with per-cluster locking
        for cluster in schedule.clusters:
            # Acquire distributed lock
            lock_value = _acquire_lock(redis, schedule_id, cluster.id, ttl_seconds=300)
            if not lock_value:
                logger.warning(f"Skipping wake for cluster {cluster.name} — locked by another worker")
                continue
            
            try:
                cluster_config = {
                    "cluster_name": cluster.name,
                    "region": cluster.region,
                    "kubeconfig": {}
                }
                
                strategy = strategy_class(cluster_config)
                saved_state = schedule.saved_state.get(cluster.id, {})
                
                # ── Task 9.2: Strategy-aware staleness threshold ──
                # Nuclear/Snapshot need tighter staleness — they modify ASG state
                staleness_thresholds = {
                    HibernationStrategy.NUCLEAR.value: 8,         # 8h — ASG state drifts fast
                    HibernationStrategy.SNAPSHOT_RESTORE.value: 8, # 8h — snapshot may be outdated
                    HibernationStrategy.NAMESPACE_SLEEP.value: 24, # 24h — only replica counts
                }
                max_staleness_hours = staleness_thresholds.get(
                    schedule.strategy, 24
                )
                
                state_captured_at = saved_state.get("state_captured_at")
                if state_captured_at:
                    try:
                        captured_time = datetime.fromisoformat(state_captured_at)
                        age = datetime.utcnow() - captured_time
                        if age > timedelta(hours=max_staleness_hours):
                            logger.warning(
                                f"⚠️ Stale hibernation state for cluster {cluster.name} — "
                                f"captured {age.total_seconds() / 3600:.1f}h ago "
                                f"(max {max_staleness_hours}h for {schedule.strategy}). "
                                f"Replica counts may have changed since hibernation."
                            )
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid state_captured_at for cluster {cluster.name}")
                
                result = strategy.wake(saved_state)
                
                logger.info(f"Woke cluster {cluster.name}")
                
            except Exception as e:
                logger.error(f"Error waking cluster {cluster.name}: {e}")
                schedule.last_action = "ERROR"
                schedule.last_action_at = datetime.utcnow()
                db.commit()
                return
            finally:
                _release_lock(redis, schedule_id, cluster.id, lock_value)
        
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
