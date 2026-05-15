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
from backend.services.karpenter_metrics_collector import KarpenterMetricsCollector
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
    """Every 10 min: Scan clusters for node classification (with jitter) + WIE slow loop"""
    try:
        redis_client = get_redis_client()
        svc = WorkloadInspector(redis=redis_client)
        clusters = get_active_clusters()
        
        for cluster in clusters:
            try:
                # Add jitter using WorkloadInspector's logic (or sleep locally)
                import time
                time.sleep(random.randint(0, 10)) # Small local jitter to spread DB load
                classification = svc.scan_cluster(cluster.id)
                logger.debug(f"[Scheduler] Scanned cluster {cluster.id}, got {len(classification or {})} nodes")

                # E1: Build per-controller workload profiles + misconfig recommendations
                try:
                    svc.build_all_profiles_for_cluster(cluster.id)
                except Exception as _wp_err:
                    logger.warning(f"[Scheduler] Workload profile build failed for {cluster.id}: {_wp_err}")

                # WIE v4.3 slow loop — full classification, DB + Redis writes
                try:
                    from backend.pipeline.stage2_wie.engine import WorkloadIdentificationEngine
                    db = SessionLocal()
                    try:
                        engine = WorkloadIdentificationEngine(redis=redis_client, db=db, k8s_client=None)
                        engine.slow_loop_classify(cluster_id=cluster.id)
                        logger.debug(f"[Scheduler] WIE slow loop complete for cluster {cluster.id}")
                    finally:
                        db.close()
                except Exception as _wie_err:
                    logger.warning(f"[Scheduler] WIE slow loop failed for cluster {cluster.id}: {_wie_err}")

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


def job_wie_fast_loop():
    """Every 2 min: WIE fast loop — update pod_state cache (restarts, ready count, zones)"""
    try:
        redis_client = get_redis_client()
        clusters = get_active_clusters()

        for cluster in clusters:
            try:
                from backend.pipeline.stage2_wie.engine import WorkloadIdentificationEngine
                db = SessionLocal()
                try:
                    engine = WorkloadIdentificationEngine(redis=redis_client, db=db, k8s_client=None)
                    engine.fast_loop_update(cluster_id=cluster.id)
                    logger.debug(f"[Scheduler] WIE fast loop complete for cluster {cluster.id}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"[Scheduler] WIE fast loop failed for cluster {cluster.id}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] WIE fast loop job failed: {e}")

def job_karpenter_metrics_collection():
    """Every 2 mins: Collect Karpenter provision success rates and p90s (Tasks 2.3/2.4)"""
    try:
        redis_client = get_redis_client()
        clusters = get_active_clusters()
        db = SessionLocal()
        try:
            collector = KarpenterMetricsCollector(db=db, redis_client=redis_client)
            for cluster in clusters:
                collector.collect_metrics_for_cluster(cluster.id)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Scheduler] Karpenter metrics collection job failed: {e}")

# =========================================================================
# Scheduler Initialization
# =========================================================================

def job_run_placement_cycle():
    """Every 10 min: Run placement advisor cycle for active clusters"""
    from backend.core.config import settings
    if not settings.FEATURE_PLACEMENT_ADVISOR_ENABLED:
        return
        
    try:
        from backend.workers.tasks.placement_advisor_task import run_placement_cycle_task
        redis_client = get_redis_client()
        clusters = get_active_clusters()
        
        for cluster in clusters:
            # Guard: check if WIE has completed at least one scan
            wie_key = f"spot:wie:metrics:{cluster.id}"
            if not redis_client.exists(wie_key):
                logger.debug(f"[Scheduler] Skipping placement cycle for {cluster.id} - WIE metrics not found")
                continue
                
            logger.info(f"[Scheduler] Dispatching placement advisor cycle for {cluster.id}")
            run_placement_cycle_task.apply_async(args=[cluster.id])
            
    except Exception as e:
        logger.error(f"[Scheduler] Failed placement advisor cycle dispatch: {e}")

def job_reconcile_nodepool_classes():
    """Every 10 min: Reconcile Karpenter NodePool classes (throttled internally to 30m / 6h)"""
    from backend.core.config import settings
    if not settings.FEATURE_PLACEMENT_ADVISOR_ENABLED:
        return
        
    try:
        from backend.workers.tasks.reconciliation_worker import reconcile_nodepool_classes_task
        logger.info(f"[Scheduler] Dispatching NodePool classes reconciliation")
        reconcile_nodepool_classes_task.apply_async()
    except Exception as e:
        logger.error(f"[Scheduler] Failed NodePool classes reconciliation dispatch: {e}")

def start_scheduler():
    """Initialize and start the background scheduler"""
    if scheduler.running:
        return
        
    logger.info("Starting background scheduler for Decision Engine v3...")

    # Delay first run by 60s so uvicorn can start serving HTTP before
    # scheduler jobs consume the thread pool.
    from datetime import datetime, timedelta
    first_run = datetime.now() + timedelta(seconds=60)
    
    # 1. Refresh active cluster count (Every 5 minutes)
    scheduler.add_job(
        job_refresh_active_count,
        trigger=IntervalTrigger(minutes=5),
        id="refresh_active_count",
        replace_existing=True,
        next_run_time=first_run,
    )
    
    # 2. Reconcile stuck substitutes (Every 5 minutes)
    scheduler.add_job(
        job_reconcile_substitutes,
        trigger=IntervalTrigger(minutes=5),
        id="reconcile_substitutes",
        replace_existing=True,
        next_run_time=first_run,
    )
    
    # 3. Scan clusters for classification (Every 10 minutes)
    scheduler.add_job(
        job_scan_clusters,
        trigger=IntervalTrigger(minutes=10),
        id="scan_clusters",
        replace_existing=True,
        next_run_time=first_run + timedelta(seconds=10),
    )
    
    # 4. Check cost drift (Every 30 minutes)
    scheduler.add_job(
        job_check_cost_drift,
        trigger=IntervalTrigger(minutes=30),
        id="check_cost_drift",
        replace_existing=True,
        next_run_time=first_run + timedelta(seconds=20),
    )
    
    # 5. Detect Volatility Regimes (Hourly)
    scheduler.add_job(
        job_detect_volatility,
        trigger=IntervalTrigger(hours=1),
        id="detect_volatility",
        replace_existing=True,
        next_run_time=first_run + timedelta(seconds=30),
    )
    
    # 6. / 7. Blacklist cleanup and Redis hygiene (Daily at 2 AM)
    scheduler.add_job(
        job_cleanup_blacklist,
        trigger=CronTrigger(hour=2, minute=0),
        id="cleanup_blacklist",
        replace_existing=True,
    )

    # 7. WIE fast loop — pod_state cache updates (Every 2 minutes)
    scheduler.add_job(
        job_wie_fast_loop,
        trigger=IntervalTrigger(minutes=2),
        id="wie_fast_loop",
        replace_existing=True,
        max_instances=1,
        next_run_time=first_run + timedelta(seconds=40),
    )
    
    # Task 2.3 / 2.4: Karpenter metrics collection (Every 2 minutes)
    scheduler.add_job(
        job_karpenter_metrics_collection,
        trigger=IntervalTrigger(minutes=2),
        id="karpenter_metrics_collection",
        replace_existing=True,
        max_instances=1,
        next_run_time=first_run + timedelta(seconds=45),
    )
    
    # 8. Placement Advisor cycle (Every 10 minutes)
    scheduler.add_job(
        job_run_placement_cycle,
        trigger=IntervalTrigger(minutes=10),
        id="run_placement_cycle",
        replace_existing=True,
        max_instances=1,
        next_run_time=first_run + timedelta(seconds=50),
    )
    
    # Task 2.1: NodePool Class Reconciler (Every 10 minutes)
    scheduler.add_job(
        job_reconcile_nodepool_classes,
        trigger=IntervalTrigger(minutes=10),
        id="reconcile_nodepool_classes",
        replace_existing=True,
        max_instances=1,
        next_run_time=first_run + timedelta(seconds=55),
    )
    
    scheduler.start()
    logger.info("Background scheduler started successfully.")

def stop_scheduler():
    """Shutdown the background scheduler gracefully"""
    if scheduler.running:
        logger.info("Shutting down background scheduler...")
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown complete.")
