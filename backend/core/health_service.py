"""
Health Service
System health monitoring and diagnostics

Monitors the health of the Spot Optimizer platform including:
- Database connectivity
- Redis connectivity
- Celery workers
- AWS API access
- Data freshness
- System metrics

Provides health check endpoints and alerts for system issues.

Dependencies:
- Database session
- Redis client
- Celery app
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import time

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.models.base import get_db
from backend.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class HealthStatus:
    """Health status constants"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthService:
    """
    System health monitoring service
    """

    def __init__(self, db: Session = None, redis_client=None):
        """
        Initialize Health Service

        Args:
            db: Optional database session
            redis_client: Optional Redis client
        """
        self.db = db
        self.redis_client = redis_client

    def check_overall_health(self) -> Dict[str, Any]:
        """
        Comprehensive health check of all system components

        Returns:
            Dict with health status for each component
        """
        logger.info("[HEALTH] Running comprehensive health check")

        start_time = time.time()

        # Check all components
        checks = {
            "database": self._check_database(),
            "redis": self._check_redis(),
            "celery": self._check_celery(),
            "data_freshness": self._check_data_freshness(),
            "aws_connectivity": self._check_aws_connectivity()
        }

        # Determine overall status
        all_healthy = all(c["status"] == HealthStatus.HEALTHY for c in checks.values())
        any_unhealthy = any(c["status"] == HealthStatus.UNHEALTHY for c in checks.values())

        if all_healthy:
            overall_status = HealthStatus.HEALTHY
        elif any_unhealthy:
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED

        elapsed = time.time() - start_time

        result = {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "response_time_ms": int(elapsed * 1000),
            "checks": checks
        }

        logger.info(f"[HEALTH] Health check complete: {overall_status} ({elapsed:.2f}s)")

        return result

    def _check_database(self) -> Dict[str, Any]:
        """
        Check database connectivity and performance

        Returns:
            Dict with database health status
        """
        try:
            db = self.db or next(get_db())

            start = time.time()

            # Execute simple query
            result = db.execute(text("SELECT 1"))
            result.fetchone()

            query_time = (time.time() - start) * 1000  # ms

            # Check query performance
            if query_time > 1000:
                status = HealthStatus.DEGRADED
                message = f"Slow database response: {query_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "Database connection OK"

            return {
                "status": status,
                "message": message,
                "response_time_ms": int(query_time)
            }

        except Exception as e:
            logger.error(f"[HEALTH] Database health check failed: {str(e)}")
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"Database error: {str(e)}",
                "response_time_ms": None
            }

    def _check_redis(self) -> Dict[str, Any]:
        """
        Check Redis connectivity and performance

        Returns:
            Dict with Redis health status
        """
        try:
            redis_client = self.redis_client or get_redis_client()

            start = time.time()

            # Execute PING command
            response = redis_client.ping()

            ping_time = (time.time() - start) * 1000  # ms

            if not response:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": "Redis PING failed",
                    "response_time_ms": int(ping_time)
                }

            # Check response time
            if ping_time > 100:
                status = HealthStatus.DEGRADED
                message = f"Slow Redis response: {ping_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "Redis connection OK"

            # Check memory usage
            info = redis_client.info('memory')
            used_memory_mb = info.get('used_memory', 0) / (1024 * 1024)
            max_memory_mb = info.get('maxmemory', 0) / (1024 * 1024)

            memory_info = {
                "used_mb": int(used_memory_mb),
                "max_mb": int(max_memory_mb) if max_memory_mb > 0 else None
            }

            return {
                "status": status,
                "message": message,
                "response_time_ms": int(ping_time),
                "memory": memory_info
            }

        except Exception as e:
            logger.error(f"[HEALTH] Redis health check failed: {str(e)}")
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"Redis error: {str(e)}",
                "response_time_ms": None
            }

    def _check_celery(self) -> Dict[str, Any]:
        """
        Check Celery worker health

        Returns:
            Dict with Celery health status
        """
            # Import Celery app
            from backend.workers import app as celery_app

            # Get active workers
            inspect = celery_app.control.inspect()

            # Check active workers
            active_workers = inspect.active()

            if not active_workers:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": "No active Celery workers found",
                    "worker_count": 0
                }

            worker_count = len(active_workers)

            # Check registered tasks
            registered_tasks = inspect.registered()

            total_tasks = sum(len(tasks) for tasks in registered_tasks.values()) if registered_tasks else 0

            return {
                "status": HealthStatus.HEALTHY,
                "message": f"{worker_count} active workers",
                "worker_count": worker_count,
                "registered_tasks": total_tasks
            }

        except Exception as e:
            logger.error(f"[HEALTH] Celery health check failed: {str(e)}")
            return {
                "status": HealthStatus.DEGRADED,
                "message": f"Celery check error: {str(e)}",
                "worker_count": None
            }

    def _check_data_freshness(self) -> Dict[str, Any]:
        """
        Check data freshness (pricing, advisor data, etc.)

        Returns:
            Dict with data freshness status
        """
        try:
            redis_client = self.redis_client or get_redis_client()

            # Check Spot price freshness
            # Sample key: spot_price:us-east-1:us-east-1a:m5.large
            sample_key = None
            for key in redis_client.scan_iter(match="spot_price:*", count=1):
                sample_key = key
                break

            if sample_key:
                # Check TTL
                ttl = redis_client.ttl(sample_key)

                # Expected TTL is 600 seconds (10 min)
                # If TTL is low, data is fresh
                if ttl > 300:
                    status = HealthStatus.HEALTHY
                    message = "Pricing data is fresh"
                elif ttl > 0:
                    status = HealthStatus.DEGRADED
                    message = f"Pricing data aging (TTL: {ttl}s)"
                else:
                    status = HealthStatus.UNHEALTHY
                    message = "Pricing data expired"

                return {
                    "status": status,
                    "message": message,
                    "sample_key": sample_key.decode() if isinstance(sample_key, bytes) else sample_key,
                    "ttl_seconds": ttl
                }
            else:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": "No pricing data found in cache",
                    "sample_key": None,
                    "ttl_seconds": None
                }

        except Exception as e:
            logger.error(f"[HEALTH] Data freshness check failed: {str(e)}")
            return {
                "status": HealthStatus.DEGRADED,
                "message": f"Freshness check error: {str(e)}"
            }

    def _check_aws_connectivity(self) -> Dict[str, Any]:
        """
        Check AWS API connectivity

        Returns:
            Dict with AWS connectivity status
        """
        try:
            # Try to get caller identity (doesn't require specific permissions)
            sts_client = boto3.client('sts')

            start = time.time()
            response = sts_client.get_caller_identity()
            api_time = (time.time() - start) * 1000

            account_id = response.get('Account')

            if api_time > 2000:
                status = HealthStatus.DEGRADED
                message = f"Slow AWS API response: {api_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "AWS API connectivity OK"

            return {
                "status": status,
                "message": message,
                "response_time_ms": int(api_time),
                "account_id": account_id
            }

        except ClientError as e:
            logger.error(f"[HEALTH] AWS connectivity check failed: {str(e)}")
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"AWS API error: {str(e)}",
                "response_time_ms": None
            }

        except Exception as e:
            logger.error(f"[HEALTH] AWS connectivity check failed: {str(e)}")
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"AWS error: {str(e)}",
                "response_time_ms": None
            }

    def check_readiness(self) -> Dict[str, Any]:
        """
        Readiness check (can the service handle requests?)

        Lighter than full health check - only checks critical components.

        Returns:
            Dict with readiness status
        """
        # Check database and Redis only
        db_check = self._check_database()
        redis_check = self._check_redis()

        is_ready = (
            db_check["status"] != HealthStatus.UNHEALTHY and
            redis_check["status"] != HealthStatus.UNHEALTHY
        )

        return {
            "ready": is_ready,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "database": db_check,
                "redis": redis_check
            }
        }

    def check_liveness(self) -> Dict[str, Any]:
        """
        Liveness check (is the service running?)

        Minimal check - just confirms the service is responsive.

        Returns:
            Dict with liveness status
        """
        return {
            "alive": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get system metrics

        Returns:
            Dict with system metrics
        """
        try:
            db = self.db or next(get_db())
            redis_client = self.redis_client or get_redis_client()

            # Get database stats
            from backend.models import Cluster, Account

            cluster_count = db.query(Cluster).count()
            account_count = db.query(Account).count()

            # Get Redis stats
            redis_info = redis_client.info()

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "database": {
                    "clusters": cluster_count,
                    "accounts": account_count
                },
                "redis": {
                    "used_memory_mb": int(redis_info.get('used_memory', 0) / (1024 * 1024)),
                    "connected_clients": redis_info.get('connected_clients', 0),
                    "total_commands_processed": redis_info.get('total_commands_processed', 0)
                }
            }

        except Exception as e:
            logger.error(f"[HEALTH] Error getting metrics: {str(e)}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }


def get_health_service(db: Session = None, redis_client=None) -> HealthService:
    """
    Factory function to create Health Service instance

    Args:
        db: Optional database session
        redis_client: Optional Redis client

    Returns:
        HealthService instance
    """
    return HealthService(db, redis_client)
