"""
Cost Calculator Task
Calculates cluster costs from instance prices and updates the database
"""
import logging
from datetime import datetime
from celery import Task
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.workers import app
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.models.instance import Instance

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.cost.calculate_cluster_costs")
def calculate_cluster_costs(self: Task):
    """
    Calculate cluster monthly costs from instance prices.

    This task runs periodically to keep cluster costs in sync with instance prices.
    Useful when Cost Explorer data is unavailable or delayed.

    Returns:
        {
            "clusters_updated": 5,
            "total_cost": 1250.00
        }
    """
    db = next(get_db())

    try:
        logger.info("[COST-CALC] Starting cluster cost calculation...")

        # Get all clusters
        clusters = db.query(Cluster).all()
        clusters_updated = 0
        total_cost = 0.0

        for cluster in clusters:
            # Calculate total monthly cost from instances
            cluster_cost = db.query(func.sum(Instance.price)).filter(
                Instance.cluster_id == cluster.id,
                Instance.price.isnot(None)
            ).scalar()

            if cluster_cost is None:
                cluster_cost = 0.0

            # Only update if cost changed
            if cluster.monthly_cost != int(cluster_cost):
                old_cost = cluster.monthly_cost or 0
                cluster.monthly_cost = int(cluster_cost)
                cluster.updated_at = datetime.utcnow()
                clusters_updated += 1
                total_cost += cluster_cost

                logger.info(
                    f"[COST-CALC] Updated {cluster.name}: "
                    f"${old_cost} -> ${cluster_cost:.2f}"
                )

        db.commit()

        result = {
            "clusters_updated": clusters_updated,
            "total_cost": round(total_cost, 2)
        }

        logger.info(
            f"[COST-CALC] Complete: Updated {clusters_updated} clusters, "
            f"Total cost: ${total_cost:.2f}"
        )

        return result

    except Exception as e:
        logger.error(f"[COST-CALC] Error calculating cluster costs: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
