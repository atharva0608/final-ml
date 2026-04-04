"""
ASCPAi Celery Workers - Pool Selection & Spot Price Collection

Scheduled Tasks:
1. execute_pool_ranking_pipeline - Runs 8-step pool selection every 1 hour
2. collect_spot_prices - Collects historical spot prices every 10 minutes
3. warm_global_cache - Pre-warms global pool cache every hour
4. check_ondemand_fallback_expiry - Checks on-demand fallback TTLs every 30 minutes
5. cleanup_blacklist - Cleans expired blacklist entries every hour
"""

from celery import Task
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

from backend.workers.app import app
from backend.models.base import get_db
from backend.core.redis_client import get_redis_client
from backend.services.pool_ranking_service import PoolRankingService, NodeTemplate
from backend.models.pricing import SpotPriceHistory

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.ascpai.execute_pool_ranking_pipeline")
def execute_pool_ranking_pipeline(self: Task) -> Dict[str, Any]:
    """
    Execute ASCPAi 8-step pool selection pipeline.

    Runs every 1 hour to provide ML-ranked pool recommendations.

    Steps:
    1. Node Template Filtering
    2. AZ Filtering
    3. Spot Advisor Filter
    4. Global Blacklist Check
    5. Capacity Check
    6. Price Fetch
    7. ML Model Scoring
    8. Final Ranking & Caching

    Returns:
        Dict with execution statistics
    """
    logger.info("[ASCPAi] Starting pool ranking pipeline execution")

    db = next(get_db())
    redis = get_redis_client()

    try:
        # Default node template (can be customized per organization)
        default_template = NodeTemplate(
            architecture=["amd64", "arm64"],
            vcpu_range=(2, 16),
            memory_range=(4, 64),
            allowed_families=["m5", "m6i", "c5", "c6i", "r5", "r6i"],
            allowed_sizes=["large", "xlarge", "2xlarge", "4xlarge"],
            allowed_azs=None,  # All AZs
            excluded_instance_types=["*.metal", "*.24xlarge"]
        )

        # Execute pipeline
        service = PoolRankingService(db, redis)
        ranked_pools = service.rank_pools(
            node_template=default_template,
            region="ap-south-1",
            limit=20
        )

        logger.info(f"[ASCPAi] Pipeline complete: {len(ranked_pools)} pools ranked")

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "pools_ranked": len(ranked_pools),
            "top_pool": {
                "instance_type": ranked_pools[0].pool.instance_type if ranked_pools else None,
                "az": ranked_pools[0].pool.az if ranked_pools else None,
                "ml_score": float(ranked_pools[0].ml_score) if ranked_pools else None
            } if ranked_pools else None
        }

    except Exception as e:
        logger.error(f"[ASCPAi] Pipeline execution failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()


@app.task(bind=True, name="workers.ascpai.collect_spot_prices")
def collect_spot_prices(self: Task) -> Dict[str, Any]:
    """
    Collect current spot prices from AWS and store in spot_price_history table.

    Runs every 10 minutes to build historical data for ML features:
    - Lag features (1h, 4h, 24h lookback)
    - Rolling features (4h, 24h windows)
    - Price dynamics (velocity, volatility)

    Maintains 24-hour rolling buffer (144 data points per pool).

    Returns:
        Dict with collection statistics
    """
    logger.info("[ASCPAi] Starting spot price collection")

    db = next(get_db())

    try:
        # TODO: Implement AWS EC2 describe_spot_price_history API call
        # For now, this is a placeholder

        timestamp = datetime.utcnow()
        prices_collected = 0

        # Example: Collect prices for monitored instance types
        monitored_pools = [
            ("m5.xlarge", "aps1-az1", "ap-south-1"),
            ("c5.xlarge", "aps1-az2", "ap-south-1"),
            ("r5.2xlarge", "aps1-az3", "ap-south-1"),
        ]

        for instance_type, az, region in monitored_pools:
            # Fetch current spot price from AWS API
            # spot_price = fetch_spot_price_from_aws(instance_type, az, region)
            # ondemand_price = fetch_ondemand_price(instance_type, region)

            # Placeholder values
            spot_price = 0.045  # Mock
            ondemand_price = 0.096  # Mock
            savings = (ondemand_price - spot_price) / ondemand_price

            # Store in database
            price_entry = SpotPriceHistory(
                instance_type=instance_type,
                az=az,
                region=region,
                timestamp=timestamp,
                spot_price=spot_price,
                ondemand_price=ondemand_price,
                savings=savings
            )

            db.add(price_entry)
            prices_collected += 1

        db.commit()

        # Cleanup old data (keep only last 24 hours = 144 entries per pool)
        cleanup_old_spot_prices(db)

        logger.info(f"[ASCPAi] Collected {prices_collected} spot prices")

        return {
            "status": "success",
            "timestamp": timestamp.isoformat(),
            "prices_collected": prices_collected
        }

    except Exception as e:
        logger.error(f"[ASCPAi] Spot price collection failed: {e}")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()


def cleanup_old_spot_prices(db):
    """Delete spot price entries older than 24 hours."""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        deleted_count = db.query(SpotPriceHistory).filter(
            SpotPriceHistory.timestamp < cutoff_time
        ).delete()

        db.commit()

        if deleted_count > 0:
            logger.info(f"[ASCPAi] Cleaned up {deleted_count} old spot price entries")

    except Exception as e:
        logger.error(f"[ASCPAi] Cleanup failed: {e}")
        db.rollback()


@app.task(bind=True, name="workers.ascpai.compute_family_baselines")
def compute_family_baselines(self: Task) -> Dict[str, Any]:
    """
    Compute family-hour baselines from historical spot price data.

    This task should be run:
    - Once initially to populate the table
    - Weekly to update baselines with fresh data

    Computes statistics per (instance_family, hour, day_of_week):
    - hour_avg_savings
    - hour_std_savings
    - dow_avg_savings
    - weekend_avg_savings

    Returns:
        Dict with computation statistics
    """
    logger.info("[ASCPAi] Starting family baseline computation")

    db = next(get_db())

    try:
        # TODO: Implement family baseline computation
        # This requires aggregating historical spot_price_history data

        # Placeholder
        logger.info("[ASCPAi] Family baseline computation not yet implemented")

        return {
            "status": "pending",
            "message": "Not yet implemented",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"[ASCPAi] Family baseline computation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()


@app.task(bind=True, name="workers.ascpai.sync_karpenter_nodepools")
def sync_karpenter_nodepools(self: Task) -> Dict[str, Any]:
    """
    Syncs ML-ranked instance types to Karpenter NodePools.

    Runs every 1 hour (after pool ranking completes) to keep Karpenter NodePools updated with:
    - Top 10 ML-approved instance types
    - Safest availability zones
    - Latest pool rankings from ML pipeline

    This ensures Karpenter only provisions nodes from safe, cheap pools.

    Returns:
        Dict with sync statistics
    """
    logger.info("[Karpenter] Starting NodePool sync")

    db = next(get_db())
    redis = get_redis_client()

    try:
        from backend.services.karpenter_service import KarpenterService
        from backend.models.cluster import Cluster

        karpenter_service = KarpenterService(db, redis)

        # Get all active EKS clusters
        clusters = db.query(Cluster).filter(
            Cluster.cluster_type == 'EKS',
            Cluster.status == 'ACTIVE'
        ).all()

        if not clusters:
            logger.info("[Karpenter] No active EKS clusters found")
            return {
                "status": "success",
                "message": "No active EKS clusters to sync",
                "timestamp": datetime.utcnow().isoformat()
            }

        synced_count = 0
        failed_count = 0

        for cluster in clusters:
            # Skip clusters without an active agent heartbeat — NodePool sync requires
            # Karpenter to be running. A cluster with no recent heartbeat is either a
            # ghost cluster (agent removed / cluster deleted) or an unreachable endpoint.
            # Avoids repeated 404/connection-refused errors in the worker logs.
            if cluster.agent_installed != 'Y':
                continue
            # Skip clusters where Karpenter is not installed — no NodePool CRDs to sync
            if not cluster.karpenter_mode:
                continue
            if cluster.last_heartbeat:
                from datetime import timezone
                _hb = cluster.last_heartbeat
                if _hb.tzinfo is None:
                    _hb = _hb.replace(tzinfo=timezone.utc)
                _mins_since_hb = (datetime.now(timezone.utc) - _hb).total_seconds() / 60
                if _mins_since_hb > 30:
                    logger.debug(
                        f"[Karpenter] Skipping {cluster.name} — last heartbeat {_mins_since_hb:.0f} min ago"
                    )
                    continue
            else:
                # agent_installed='Y' but no heartbeat ever received — skip
                continue
            try:
                # Get ML rankings for this cluster's region
                # Use cached rankings from Redis (updated by pool ranking pipeline)
                ranking_service = PoolRankingService(db, redis)

                default_template = NodeTemplate(
                    architecture=["amd64", "arm64"],
                    vcpu_range=(2, 16),
                    memory_range=(4, 64),
                    allowed_families=["m5", "m6i", "c5", "c6i", "r5", "r6i"],
                    allowed_sizes=["large", "xlarge", "2xlarge", "4xlarge"],
                    allowed_azs=None,
                    excluded_instance_types=["*.metal", "*.24xlarge"]
                )

                ranked_pools = ranking_service.rank_pools(
                    node_template=default_template,
                    region=cluster.region,
                    limit=10  # Top 10 pools
                )

                if not ranked_pools:
                    logger.warning(f"[Karpenter] No ranked pools for cluster {cluster.name}")
                    continue

                # Convert to format expected by Karpenter service
                top_pools = []
                for scored_pool in ranked_pools:
                    top_pools.append({
                        'instance_type': scored_pool.pool.instance_type,
                        'az': scored_pool.pool.az,
                        'ml_score': float(scored_pool.ml_score)
                    })

                # Sync to Karpenter NodePool
                result = karpenter_service.sync_ml_rankings_to_nodepool(
                    cluster_id=cluster.id,
                    top_pools=top_pools,
                    nodepool_name='default'
                )

                if result['status'] == 'success':
                    synced_count += 1
                    logger.info(f"[Karpenter] Synced NodePool for cluster {cluster.name} ({len(top_pools)} instance types)")
                else:
                    failed_count += 1
                    logger.error(f"[Karpenter] Failed to sync cluster {cluster.name}: {result.get('error')}")

            except Exception as e:
                failed_count += 1
                logger.error(f"[Karpenter] Failed to sync cluster {cluster.name}: {e}")

        logger.info(f"[Karpenter] NodePool sync complete: {synced_count} synced, {failed_count} failed")

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "clusters_synced": synced_count,
            "clusters_failed": failed_count,
            "total_clusters": len(clusters)
        }

    except Exception as e:
        logger.error(f"[Karpenter] NodePool sync failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()
