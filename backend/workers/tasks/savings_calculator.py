"""
Savings Calculator Task
Calculates real potential and realized savings based on current spot/on-demand prices
"""
import logging
from datetime import datetime
from celery import Task
from sqlalchemy.orm import Session
from typing import Dict, List

from backend.workers import app
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.models.instance import Instance, InstanceLifecycle
from backend.utils.pricing_helper import get_pricing_helper

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.savings.calculate_real_savings")
def calculate_real_savings(self: Task):
    """
    Calculate real potential and realized savings based on actual spot/on-demand prices.

    Logic:
    - Potential Savings: What we COULD save by switching ON_DEMAND instances to SPOT
      Formula: SUM((OD_price - Spot_price) for each ON_DEMAND instance)

    - Realized Savings: What we're ALREADY saving from current SPOT instances
      Formula: SUM((OD_price - Spot_price) for each SPOT instance)

    Uses real spot prices from AWS API with 12-hour Redis cache.
    Falls back to 65% discount estimate if API unavailable.

    Returns:
        {
            "clusters_updated": 5,
            "total_potential_savings": 1250.00,
            "total_realized_savings": 850.00
        }
    """
    db = next(get_db())
    pricing_helper = get_pricing_helper()

    try:
        logger.info("[SAVINGS-CALC] Starting real savings calculation...")

        # Get all clusters
        clusters = db.query(Cluster).all()
        clusters_updated = 0
        total_potential = 0.0
        total_realized = 0.0

        for cluster in clusters:
            # Get all RUNNING instances for this cluster (exclude terminated)
            instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running',
            ).all()

            if not instances:
                logger.debug(f"[SAVINGS-CALC] No instances found for cluster {cluster.name}")
                continue

            # Group instances by lifecycle
            on_demand_instances = [i for i in instances if i.lifecycle == InstanceLifecycle.ON_DEMAND]
            
            # Issue #3: Only count spot instances launched by the platform to avoid 
            # inflating savings with pre-existing or independently managed spot nodes
            platform_flags = ("platform", "spot-optimizer-direct")
            spot_instances = [
                i for i in instances 
                if i.lifecycle == InstanceLifecycle.SPOT and i.launched_by in platform_flags
            ]

            # Calculate savings
            potential_savings = 0.0
            realized_savings = 0.0

            # Calculate potential savings (ON_DEMAND instances)
            for instance in on_demand_instances:
                try:
                    # Get on-demand price (already stored in instance.price)
                    od_price = float(instance.price or 0)

                    if od_price == 0:
                        # Fallback: calculate on-demand price
                        od_price = pricing_helper.get_ec2_price(
                            cluster.region or 'us-east-1',
                            instance.instance_type
                        )

                    # Get spot price (with 12-hour cache)
                    spot_price = pricing_helper.get_spot_price(
                        cluster.region or 'us-east-1',
                        instance.instance_type,
                        instance.az
                    )

                    # Calculate savings for this instance
                    savings = max(0, od_price - spot_price)
                    potential_savings += savings

                    logger.debug(
                        f"[SAVINGS-CALC] {instance.instance_type} (ON_DEMAND): "
                        f"OD=${od_price:.2f}, Spot=${spot_price:.2f}, "
                        f"Potential=${savings:.2f}"
                    )

                except Exception as e:
                    logger.warning(
                        f"[SAVINGS-CALC] Error calculating potential savings for "
                        f"{instance.instance_id}: {e}"
                    )

            # Calculate realized savings (SPOT instances)
            for instance in spot_instances:
                try:
                    # Get on-demand price for comparison
                    od_price = pricing_helper.get_ec2_price(
                        cluster.region or 'us-east-1',
                        instance.instance_type
                    )

                    # Get actual spot price
                    spot_price = pricing_helper.get_spot_price(
                        cluster.region or 'us-east-1',
                        instance.instance_type,
                        instance.az
                    )

                    # Calculate savings we're already getting
                    savings = max(0, od_price - spot_price)
                    realized_savings += savings

                    logger.debug(
                        f"[SAVINGS-CALC] {instance.instance_type} (SPOT): "
                        f"OD=${od_price:.2f}, Spot=${spot_price:.2f}, "
                        f"Realized=${savings:.2f}"
                    )

                except Exception as e:
                    logger.warning(
                        f"[SAVINGS-CALC] Error calculating realized savings for "
                        f"{instance.instance_id}: {e}"
                    )

            # Update cluster with calculated savings
            old_potential = cluster.potential_savings_monthly or 0
            old_realized = cluster.realized_savings_monthly or 0

            cluster.potential_savings_monthly = round(potential_savings, 2)
            cluster.realized_savings_monthly = round(realized_savings, 2)
            cluster.on_demand_node_count = len(on_demand_instances)
            cluster.spot_count = len(spot_instances)
            cluster.last_assessed = datetime.utcnow()

            # Log if changed
            if (abs(old_potential - potential_savings) > 0.01 or
                abs(old_realized - realized_savings) > 0.01):
                logger.info(
                    f"[SAVINGS-CALC] Updated {cluster.name}: "
                    f"Potential ${old_potential:.2f} → ${potential_savings:.2f}, "
                    f"Realized ${old_realized:.2f} → ${realized_savings:.2f}"
                )
                clusters_updated += 1

            total_potential += potential_savings
            total_realized += realized_savings

        db.commit()

        result = {
            "clusters_updated": clusters_updated,
            "total_potential_savings": round(total_potential, 2),
            "total_realized_savings": round(total_realized, 2)
        }

        logger.info(
            f"[SAVINGS-CALC] Complete: Updated {clusters_updated} clusters, "
            f"Potential savings: ${total_potential:.2f}, "
            f"Realized savings: ${total_realized:.2f}"
        )

        return result

    except Exception as e:
        logger.error(f"[SAVINGS-CALC] Error calculating savings: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
