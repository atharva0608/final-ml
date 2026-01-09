"""
Optimizer Worker (WORK-OPT-01)
Processes optimization jobs and executes action plans
"""
import logging
from typing import Dict, Any
from datetime import datetime
from celery import Task
from sqlalchemy.orm import Session

from backend.workers import app
from backend.models.base import get_db
from backend.core.redis_client import get_redis_client
from backend.models.optimization_job import OptimizationJob
from backend.models.cluster_policy import ClusterPolicy
from backend.modules import get_spot_optimizer, get_bin_packer
from backend.models.cluster import Cluster

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.optimization.trigger_manual")
def trigger_manual_optimization(self: Task, cluster_id: str) -> Dict[str, Any]:
    """
    Trigger manual optimization for a cluster

    Args:
        cluster_id: UUID of cluster

    Returns:
        {"job_id": "uuid", "status": "queued"}
    """
    logger.info(f"[WORK-OPT-01] Triggering manual optimization for cluster {cluster_id}")

    db = next(get_db())
    try:
        # Create optimization job
        job = OptimizationJob(
            cluster_id=cluster_id,
            status="queued",
            created_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()

        # Enqueue optimization pipeline task
        optimize_cluster.delay(str(job.id), cluster_id)

        return {
            "job_id": str(job.id),
            "status": "queued"
        }

    finally:
        db.close()


@app.task(bind=True, name="workers.optimization.optimize_cluster")
def optimize_cluster(self: Task, job_id: str, cluster_id: str) -> Dict[str, Any]:
    """
    Execute optimization pipeline for a cluster

    Pipeline:
    1. Read cluster policies
    2. Detect opportunities (MOD-SPOT-01)
    3. Analyze risk (MOD-AI-01)
    4. Generate action plan
    5. Execute actions (CORE-EXEC)

    Args:
        job_id: Optimization job UUID
        cluster_id: Cluster UUID

    Returns:
        Optimization results
    """
    logger.info(f"[WORK-OPT-01] Running optimization pipeline for cluster {cluster_id}")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        # Update job status
        job = db.query(OptimizationJob).filter(OptimizationJob.id == job_id).first()
        job.status = "running"
        db.commit()

        # 1. Read cluster policies
        policy = db.query(ClusterPolicy).filter(ClusterPolicy.cluster_id == cluster_id).first()
        config = policy.config if policy else {}

        # 2. Detect opportunities
        spot_optimizer = get_spot_optimizer(db, redis_client)
        opportunities = spot_optimizer.detect_opportunities(cluster_id)

        # 3. Analyze fragmentation
        bin_packer = get_bin_packer(db)
        fragmentation = bin_packer.analyze_fragmentation(cluster_id)

        # 4. Build action plan
        action_plan = {
            "opportunities": opportunities[:5],  # Top 5
            "fragmentation": fragmentation,
            "actions": []
        }

        # Add spot replacement actions
        for opp in opportunities[:3]:  # Top 3 opportunities
            action_plan['actions'].append({
                "type": "replace_with_spot",
                "instance_id": opp['instance_id'],
                "target_type": opp['instance_type'],
                "estimated_savings": opp['savings']
            })

        # 5. Store results
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.results = action_plan
        db.commit()

        logger.info(f"[WORK-OPT-01] Optimization complete: {len(action_plan['actions'])} actions")

        return {
            "job_id": job_id,
            "status": "completed",
            "actions_count": len(action_plan['actions']),
            "total_savings": sum(a.get('estimated_savings', 0) for a in action_plan['actions'])
        }

    except Exception as e:
        logger.error(f"[WORK-OPT-01] Optimization failed: {str(e)}")
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        db.commit()
        raise

    finally:
        db.close()
