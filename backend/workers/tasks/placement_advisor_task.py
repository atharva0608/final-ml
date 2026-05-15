import time
import logging
from celery import shared_task
from sqlalchemy.orm import Session
from datetime import datetime

from backend.db.session import SessionLocal
from backend.core.config import settings
from backend.core.redis_client import get_redis_client
from backend.redis_keys import placement_cycle_lock_key, placement_metrics_key
from backend.services.placement_advisor_service import PlacementAdvisorService
from backend.models.cluster import Cluster
# Import WorkloadClassification from WIE phase 1 model
from backend.models.workload_classification import WorkloadClassificationRecord as WorkloadClassification
from backend.models.placement_policy import PlacementPolicyRecord
from backend.services.placement_rollout_service import PlacementRolloutService

logger = logging.getLogger(__name__)
redis_client = get_redis_client()

@shared_task(name="run_placement_cycle_task", bind=True, max_retries=1)
def run_placement_cycle_task(self, cluster_id: str):
    """
    Task 1.11: Run the Placement Advisor cycle for a cluster asynchronously.
    Enforces concurrency lock and metrics emission.
    """
    if not settings.FEATURE_PLACEMENT_ADVISOR_ENABLED:
        logger.info(f"Skipping placement cycle for {cluster_id} - feature disabled")
        return "skipped - disabled"
        
    lock_key = placement_cycle_lock_key(cluster_id)
    
    # Simple Redis lock (SET NX EX)
    acquired = redis_client.set(lock_key, "locked", nx=True, ex=300)
    if not acquired:
        logger.warning(f"Placement cycle already running for cluster {cluster_id}")
        return "skipped - locked"
        
    db: Session = SessionLocal()
    start_time = time.monotonic()
    
    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f"Cluster {cluster_id} not found")
            return "error - no cluster"
            
        advisor = PlacementAdvisorService(redis_client)
        
        # Load CONFIRMED workloads
        workloads = db.query(WorkloadClassification).filter(
            WorkloadClassification.cluster_id == cluster_id,
            WorkloadClassification.confidence_state == "CONFIRMED"
        ).all()
        
        cluster_state = advisor._collect_cluster_state(cluster_id, db)
        
        def get_workload_state(workload_id):
            classification = next(w for w in workloads if w.workload_id == workload_id)
            return advisor._collect_workload_state(classification, cluster_id, db)
            
        policies = advisor.run_placement_cycle(
            cluster_id=cluster_id,
            db=db,
            env=cluster.env or "prod",
            max_ratio=settings.CLUSTER_MAX_SPOT_RATIO.get(cluster.env or "prod", 0.50),
            workloads=workloads,
            get_success_rate_fn=advisor.get_spot_scheduling_success_rate_blended,
            cluster_state=cluster_state,
            get_workload_state_fn=get_workload_state
        )
        
        duration = time.monotonic() - start_time
        
        # Task 1.17 metrics emission (part of this task too)
        metrics = {
            "last_cycle_ts": datetime.utcnow().isoformat(),
            "cycle_duration_sec": duration,
            "workloads_processed": len(workloads),
            "policies_generated": len(policies),
            "status": "success"
        }
        
        metrics_key = placement_metrics_key(cluster_id)
        redis_client.hset(metrics_key, mapping=metrics)
        redis_client.expire(metrics_key, 86400) # 24h retention
        
        return f"success - {len(policies)} policies generated in {duration:.2f}s"
        
    except Exception as e:
        logger.error(f"Placement cycle failed for {cluster_id}: {str(e)}", exc_info=True)
        metrics_key = placement_metrics_key(cluster_id)
        redis_client.hset(metrics_key, mapping={
            "last_cycle_ts": datetime.utcnow().isoformat(),
            "status": "failed",
            "last_error": str(e)
        })
        raise self.retry(exc=e, countdown=60)
        
    finally:
        db.close()
        # Release lock
        redis_client.delete(lock_key)

@shared_task(name="execute_rollout_task", bind=True, max_retries=3)
def execute_rollout_task(self, cluster_id: str, workload_id: str):
    """
    Task 3.3: Stateful rollout pipeline step for a single workload.
    """
    db: Session = SessionLocal()
    try:
        policy = db.query(PlacementPolicyRecord).filter_by(cluster_id=cluster_id, workload_id=workload_id).first()
        if not policy:
            logger.error(f"Rollout cancelled: Policy {workload_id} not found")
            return "cancelled - no policy"
            
        if not policy.rollout_eligible:
            logger.info(f"Rollout paused/cancelled: {workload_id} no longer eligible")
            return "cancelled - not eligible"
            
        if not policy.actionable:
            logger.info(f"Rollout paused/cancelled: {workload_id} not actionable")
            return "cancelled - not actionable"
            
        # Check block flag
        block_key = f"spot:placement:rollout_blocked:{cluster_id}:{workload_id}"
        if redis_client.get(block_key):
            logger.warning(f"Rollout blocked for {workload_id} due to prior failure")
            return "blocked"
            
        # Check completion
        state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
        state_raw = redis_client.get(state_key)
        current_spot = 0
        if state_raw:
            try:
                state = json.loads(state_raw)
                current_spot = state.get("current_spot_pods", 0)
            except:
                pass
                
        if current_spot >= policy.spot_target:
            logger.info(f"Rollout COMPLETE for {workload_id} ({current_spot}/{policy.spot_target})")
            return "complete"
            
        # Execute Step
        rollout_svc = PlacementRolloutService(db, redis_client)
        success = rollout_svc.execute_single_pod_rollout_step(cluster_id, policy.__dict__)
        
        if success:
            logger.info(f"Rollout step successful for {workload_id}. Scheduling next step.")
            # Schedule next step in 30 seconds
            execute_rollout_task.apply_async(args=[cluster_id, workload_id], countdown=30)
            return "step_successful"
        else:
            logger.error(f"Rollout step failed for {workload_id}")
            return "step_failed"

    except Exception as e:
        logger.error(f"Rollout task failed for {workload_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()
