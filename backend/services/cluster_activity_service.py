"""
Cluster Activity Service
========================

Maintains spot:active_cluster_count from DB — not from raw Redis guess.
Used by pool_ranking_service.py for dynamic DryRun budget scaling.
"""

from sqlalchemy.orm import Session
from redis import Redis
from datetime import datetime, timedelta
import logging

from backend.models.cluster import Cluster

logger = logging.getLogger(__name__)


class ClusterActivityService:
    """
    Maintains accurate active cluster count for DryRun budget calculation.

    DryRun budget formula: min(200, max(25, active_clusters * 2))

    This service ensures the count is based on actual DB state, not guesses.
    """

    REFRESH_INTERVAL = 300  # 5 minutes
    CACHE_KEY = "spot:active_cluster_count"

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis

    def refresh_active_count(self) -> int:
        """
        Called by scheduler every 5 minutes.

        Counts clusters with recent activity (last_heartbeat within 15 min).
        Stores in Redis with TTL = 2x refresh interval (10 min) as safety buffer.

        Returns:
            Active cluster count (minimum 1).
        """
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=15)

            active_count = self.db.query(Cluster).filter(
                Cluster.status == "ACTIVE",
                Cluster.last_heartbeat >= cutoff
            ).count()

            # Ensure minimum of 1 to avoid division by zero in budget formula
            active_count = max(1, active_count)

            # Store with TTL = 2x refresh interval as safety buffer
            self.redis.setex(
                self.CACHE_KEY,
                self.REFRESH_INTERVAL * 2,  # 10 minutes
                str(active_count)
            )

            logger.info(f"Refreshed active cluster count: {active_count}")
            return active_count

        except Exception as e:
            logger.error(f"Failed to refresh active cluster count: {e}")
            # Return cached value if exists, otherwise default to 1
            cached = self.redis.get(self.CACHE_KEY)
            return int(cached) if cached else 1

    def get_active_count(self) -> int:
        """
        Get current active count from Redis cache.

        Returns:
            Active cluster count (minimum 1).
        """
        try:
            cached = self.redis.get(self.CACHE_KEY)
            return int(cached) if cached else 1
        except Exception:
            return 1
