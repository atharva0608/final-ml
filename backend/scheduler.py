import logging
import random
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.models.base import SessionLocal
from backend.models.cluster import Cluster
from backend.core.redis_client import get_redis_client

from backend.services.cluster_activity_service import ClusterActivityService
from backend.services.workload_inspector import WorkloadInspector
from backend.services.substitute_manager import SubstituteManager
from backend.services.event_monitor import EventMonitor
from backend.services.blacklist_service import BlacklistService

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler()

def get_active_clusters():
    """Helper to get all active clusters for multi-cluster jobs"""
    db = SessionLocal()
    try:
        # Assuming we scan all clusters for now, could filter by status
        return db.query(Cluster).all()
    finally:
        db.close()

def get_active_regions():
    """Helper to get unique regions from active clusters"""
    db = SessionLocal()
    try:
        clusters = db.query(Cluster).all()
        return list({c.region for c in clusters if c.region})
    finally:
        db.close()

# =========================================================================
# Background Jobs
# =========================================================================

def job_refresh_active_count():
    """Every 5 min: Refresh active cluster count for DryRun budgets"""
    try:
        db = SessionLocal()
        redis_client = get_redis_client()
        svc = ClusterActivityService(db, redis=redis_client)
        count = svc.refresh_active_count()
        logger.info(f"[Scheduler] Refreshed active cluster count: {count}")
    except Exception as e:
        logger.error(f"[Scheduler] Failed to refresh active count: {e}")
    finally:
        db.close()

def job_scan_clusters():
    """Every 10 min: Scan clusters for node classification (with jitter)"""
    try:
        redis_client = get_redis_client()
        svc = WorkloadInspector(redis_client=redis_client)
        clusters = get_active_clusters()
        
        for cluster in clusters:
            try:
                # Add jitter using WorkloadInspector's logic (or sleep locally)
                import time
                time.sleep(random.randint(0, 10)) # Small local jitter to spread DB load
                classification = svc.scan_cluster(cluster.id)
                logger.debug(f"[Scheduler] Scanned cluster {cluster.id}, got {len(classification or {})} nodes")
            except Exception as e:
                logger.error(f"[Scheduler] Failed to scan cluster {cluster.id}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] Failed cluster scan job: {e}")

def job_reconcile_substitutes():
    """Every 5 min: Reconcile stuck substitutes"""
    try:
        db = SessionLocal()
        redis_client = get_redis_client()
        svc = SubstituteManager(db, redis_client=redis_client)
        result = svc.reconcile_stuck_substitutes()
        if result.get("reconciled_count", 0) > 0:
            logger.info(f"[Scheduler] Reconciled {result['reconciled_count']} stuck substitutes")
    except Exception as e:
        logger.error(f"[Scheduler] Failed substitute reconciliation: {e}")
    finally:
        db.close()

def job_check_cost_drift():
    """Every 30 min: Check cost drift for active substitutes"""
    try:
        db = SessionLocal()
        redis_client = get_redis_client()
        svc = SubstituteManager(db, redis_client=redis_client)
        clusters = get_active_clusters()
        
        for cluster in clusters:
            try:
                drift = svc.check_cost_drift(cluster.id)
                if drift:
                    logger.warning(f"[Scheduler] Cost drift detected for cluster {cluster.id}: {drift['drift_percent']}%")
            except Exception as e:
                logger.error(f"[Scheduler] Failed to check cost drift for cluster {cluster.id}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] Failed cost drift job: {e}")
    finally:
        db.close()

def job_detect_volatility():
    """Hourly: Detect volatility regimes per region"""
    try:
        db = SessionLocal()
        redis_client = get_redis_client()
        svc = EventMonitor(db, redis=redis_client)
        regions = get_active_regions()
        
        for region in regions:
            try:
                svc.detect_volatility_regime(region)
                logger.info(f"[Scheduler] Ran volatility detection for region {region}")
            except Exception as e:
                logger.error(f"[Scheduler] Failed volatility detection for region {region}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] Failed volatility job: {e}")
    finally:
        db.close()

def job_cleanup_blacklist():
    """Daily: Clean up expired blacklists and orphaned Redis keys"""
    try:
        redis_client = get_redis_client()
        svc = BlacklistService(redis_client)
        
        cleaned_lists = svc.cleanup_expired()
        cleaned_keys = svc.cleanup_redis_keys()
        
        logger.info(f"[Scheduler] Cleanup done: {cleaned_lists} blacklists, {cleaned_keys} orphaned keys")
    except Exception as e:
        logger.error(f"[Scheduler] Failed cleanup job: {e}")

# =========================================================================
# Scheduler Initialization
# =========================================================================

def start_scheduler():
    """Initialize and start the background scheduler"""
    if scheduler.running:
        return
        
    logger.info("Starting background scheduler for Decision Engine v3...")
    
    # 1. Refresh active cluster count (Every 5 minutes)
    scheduler.add_job(
        job_refresh_active_count,
        trigger=IntervalTrigger(minutes=5),
        id="refresh_active_count",
        replace_existing=True
    )
    
    # 2. Reconcile stuck substitutes (Every 5 minutes)
    scheduler.add_job(
        job_reconcile_substitutes,
        trigger=IntervalTrigger(minutes=5),
        id="reconcile_substitutes",
        replace_existing=True
    )
    
    # 3. Scan clusters for classification (Every 10 minutes)
    scheduler.add_job(
        job_scan_clusters,
        trigger=IntervalTrigger(minutes=10),
        id="scan_clusters",
        replace_existing=True
    )
    
    # 4. Check cost drift (Every 30 minutes)
    scheduler.add_job(
        job_check_cost_drift,
        trigger=IntervalTrigger(minutes=30),
        id="check_cost_drift",
        replace_existing=True
    )
    
    # 5. Detect Volatility Regimes (Hourly)
    scheduler.add_job(
        job_detect_volatility,
        trigger=IntervalTrigger(hours=1),
        id="detect_volatility",
        replace_existing=True
    )
    
    # 6. / 7. Blacklist cleanup and Redis hygiene (Daily at 2 AM)
    scheduler.add_job(
        job_cleanup_blacklist,
        trigger=CronTrigger(hour=2, minute=0),
        id="cleanup_blacklist",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Background scheduler started successfully.")

def stop_scheduler():
    """Shutdown the background scheduler gracefully"""
    if scheduler.running:
        logger.info("Shutting down background scheduler...")
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown complete.")
