"""
Daily Stats Aggregator Task - Rolls up cluster stats into DailyClusterStat table
"""
from celery import shared_task
from sqlalchemy.orm import Session
from datetime import date
from backend.models.base import SessionLocal
from backend.models.cluster import Cluster
from backend.models.daily_cluster_stats import DailyClusterStat
from backend.models.instance import Instance
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

@shared_task(name="backend.workers.tasks.daily_stats_aggregator.aggregate_daily_stats")
def aggregate_daily_stats():
    """Aggregates cluster metrics, costs, and instances into DailyClusterStat"""
    db = SessionLocal()
    try:
        today = date.today()
        clusters = db.query(Cluster).all()
        
        for cluster in clusters:
            # Gather nodes logic
            instances = db.query(Instance).filter(Instance.cluster_id == cluster.id).all()
            
            spot_nodes = sum(1 for i in instances if i.lifecycle and i.lifecycle.lower() == "spot")
            on_demand_nodes = sum(1 for i in instances if i.lifecycle and i.lifecycle.lower() == "on_demand" or i.lifecycle == "ON_DEMAND")
            total_nodes = len(instances)
            spot_ratio = (spot_nodes / total_nodes * 100.0) if total_nodes > 0 else 0.0
            
            monthly_cost = getattr(cluster, 'monthly_cost', 0) or 0
            daily_cost = monthly_cost / 30.0
            
            # Upsert into DailyClusterStat
            stat = db.query(DailyClusterStat).filter(
                DailyClusterStat.cluster_id == cluster.id,
                DailyClusterStat.date_stamp == today
            ).first()

            if not stat:
                stat = DailyClusterStat(
                    cluster_id=cluster.id,
                    date_stamp=today
                )
                db.add(stat)
                
            stat.total_cost = daily_cost
            stat.total_savings = getattr(cluster, 'realized_savings_monthly', 0) / 30.0
            stat.spot_nodes = spot_nodes
            stat.on_demand_nodes = on_demand_nodes
            stat.total_nodes = total_nodes
            stat.spot_ratio = spot_ratio
            
            # Performance metrics
            # Safely get metrics since they might not be natively on the schema if it's dynamic
            stat.avg_cpu_utilization = getattr(cluster, 'cpu_usage_pct', 0) if hasattr(cluster, 'cpu_usage_pct') else 0
            stat.avg_memory_utilization = getattr(cluster, 'mem_usage_pct', 0) if hasattr(cluster, 'mem_usage_pct') else 0
            
        db.commit()
        logger.info(f"Aggregated daily stats for {len(clusters)} clusters on {today}")
        return {"status": "success", "processed": len(clusters)}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error in aggregate_daily_stats: {str(e)}")
        raise
    finally:
        db.close()
