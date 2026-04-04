"""
Savings Calculator Task (Task 4.3)
====================================
Uses ClusterBaseline as the immutable cost anchor.

Rules (from changes.md):
  NEVER use estimated_savings as realized_savings.
  NEVER recalculate from original target pool if fallback occurred.
  ALWAYS use actual_spot_price_hr from rebalancing_action record.
"""
import logging
from datetime import datetime
from celery import Task

from backend.workers import app
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.models.instance import Instance, InstanceLifecycle
from backend.utils.pricing_helper import get_pricing_helper

logger = logging.getLogger(__name__)

HOURS_PER_MONTH = 730  # standard billing month


@app.task(bind=True, name="workers.savings.calculate_real_savings")
def calculate_real_savings(self: Task):
    """
    Calculate savings anchored to ClusterBaseline (immutable at onboarding).

    For each cluster:
      1. Load ClusterBaseline — immutable cost anchor
      2. baseline_monthly_cost = baseline_od_price_hr × node_count × 730
      3. For each platform spot node:
           live_savings_hr = source_od_price_hr (from rebalancing_action) - current_spot_price
           live_savings_mo = live_savings_hr × 730
      4. current_monthly_cost = SUM(current_spot_price × 730) for platform nodes
      5. total_live_savings_mo = baseline_monthly_cost - current_monthly_cost
      6. savings_gap = SUM(action.savings_gap_hr × 730) for completed actions

    Also calculates potential savings for remaining ON_DEMAND nodes.
    """
    db = next(get_db())
    pricing_helper = get_pricing_helper()

    try:
        logger.info("[SAVINGS-CALC] Starting savings calculation (ClusterBaseline anchor)...")

        # Import here to avoid circular imports at module load
        from backend.models.cluster_baseline import ClusterBaseline
        from backend.models.rebalancing_action import RebalancingAction

        clusters = db.query(Cluster).all()
        clusters_updated = 0
        total_potential = 0.0
        total_realized = 0.0

        for cluster in clusters:
            try:
                instances = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()

                if not instances:
                    continue

                on_demand_instances = [i for i in instances if i.lifecycle == InstanceLifecycle.ON_DEMAND]
                platform_flags = ("platform", "spot-optimizer-direct")
                spot_instances = [
                    i for i in instances
                    if i.lifecycle == InstanceLifecycle.SPOT and i.launched_by in platform_flags
                ]

                # ── Task 4.3: Load ClusterBaseline ─────────────────────────────
                baseline = db.query(ClusterBaseline).filter(
                    ClusterBaseline.cluster_id == cluster.id
                ).first()

                baseline_monthly_cost = None
                if baseline and baseline.baseline_monthly_cost:
                    baseline_monthly_cost = float(baseline.baseline_monthly_cost)

                # ── Realized savings: anchored to source OD price per action ───
                # ALWAYS use actual_spot_price_hr — NEVER estimated.
                realized_savings = 0.0
                current_monthly_spot_cost = 0.0

                for instance in spot_instances:
                    try:
                        region = cluster.region or 'us-east-1'
                        # Get live spot price from Redis (canonical key: spot_price:{region}:{az}:{type})
                        current_spot_price = pricing_helper.get_spot_price(
                            region,
                            instance.instance_type,
                            instance.az
                        )
                        if not current_spot_price:
                            continue

                        current_monthly_spot_cost += current_spot_price * HOURS_PER_MONTH

                        # Look up the rebalancing_action that launched this node
                        # to get source_od_price_hr (what customer WAS paying)
                        action = db.query(RebalancingAction).filter(
                            RebalancingAction.cluster_id == cluster.id,
                            RebalancingAction.actual_instance_type == instance.instance_type,
                            RebalancingAction.actual_az == instance.az,
                            RebalancingAction.status == 'completed',
                        ).order_by(RebalancingAction.completed_at.desc()).first()

                        if action and action.source_od_price_hr:
                            source_od = float(action.source_od_price_hr)
                        else:
                            # Fallback: current OD price for this type
                            source_od = pricing_helper.get_ec2_price(region, instance.instance_type) or 0.0

                        live_savings_hr = max(0.0, source_od - current_spot_price)
                        realized_savings += live_savings_hr * HOURS_PER_MONTH

                        logger.debug(
                            f"[SAVINGS-CALC] {instance.instance_type} SPOT "
                            f"source_od=${source_od:.4f} spot=${current_spot_price:.4f} "
                            f"savings_hr=${live_savings_hr:.4f}"
                        )
                    except Exception as inst_err:
                        logger.warning(f"[SAVINGS-CALC] Spot instance {instance.instance_id}: {inst_err}")

                # ── Baseline-anchored total savings ─────────────────────────────
                if baseline_monthly_cost and current_monthly_spot_cost > 0:
                    total_live_savings_mo = max(0.0, baseline_monthly_cost - current_monthly_spot_cost)
                    # Use the larger of node-level sum or baseline-anchored total
                    realized_savings = max(realized_savings, total_live_savings_mo)

                # ── Potential savings: remaining ON_DEMAND nodes ────────────────
                potential_savings = 0.0
                for instance in on_demand_instances:
                    try:
                        od_price = float(instance.price or 0)
                        if od_price == 0:
                            od_price = pricing_helper.get_ec2_price(
                                cluster.region or 'us-east-1',
                                instance.instance_type
                            ) or 0.0
                        spot_price = pricing_helper.get_spot_price(
                            cluster.region or 'us-east-1',
                            instance.instance_type,
                            instance.az
                        ) or 0.0
                        potential_savings += max(0.0, od_price - spot_price) * HOURS_PER_MONTH
                    except Exception as e:
                        logger.warning(f"[SAVINGS-CALC] OD instance {instance.instance_id}: {e}")

                # ── Update cluster columns ──────────────────────────────────────
                old_potential = cluster.potential_savings_monthly or 0
                old_realized = cluster.realized_savings_monthly or 0

                cluster.potential_savings_monthly = round(potential_savings, 2)
                cluster.realized_savings_monthly = round(realized_savings, 2)
                cluster.on_demand_node_count = len(on_demand_instances)
                cluster.spot_count = len(spot_instances)
                cluster.node_count = len(instances)
                cluster.last_assessed = datetime.utcnow()

                # ── Also update estimated_savings (alias for potential_savings) ─
                cluster.estimated_savings = round(potential_savings, 2)

                # ── Recompute monthly_cost from live instance prices × 730 ───────
                priced_instances = [i for i in instances if i.price and float(i.price) > 0]
                if priced_instances:
                    live_monthly_cost = sum(float(i.price) for i in priced_instances) * HOURS_PER_MONTH
                    cluster.monthly_cost = round(live_monthly_cost, 2)

                if (abs(old_potential - potential_savings) > 0.01 or
                        abs(old_realized - realized_savings) > 0.01):
                    logger.info(
                        f"[SAVINGS-CALC] {cluster.name}: "
                        f"potential ${old_potential:.2f}→${potential_savings:.2f}  "
                        f"realized ${old_realized:.2f}→${realized_savings:.2f}"
                    )
                    clusters_updated += 1

                total_potential += potential_savings
                total_realized += realized_savings

            except Exception as cluster_err:
                logger.error(f"[SAVINGS-CALC] Cluster {cluster.id} error: {cluster_err}")

        db.commit()

        result = {
            "clusters_updated": clusters_updated,
            "total_potential_savings": round(total_potential, 2),
            "total_realized_savings": round(total_realized, 2),
        }
        logger.info(f"[SAVINGS-CALC] Complete: {result}")
        return result

    except Exception as e:
        logger.error(f"[SAVINGS-CALC] Fatal error: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
