"""
AWS Spot Optimizer - Data Cleanup Job
======================================
Cleans up old time-series data and logs to manage database growth
"""

import logging
from datetime import datetime

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


def cleanup_old_data():
    """
    Clean up old time-series data and logs.

    This job runs daily to remove old data that is no longer needed
    for operational purposes, helping to manage database size and
    improve query performance.

    Data retention policies:
    - spot_price_snapshots: 30 days
    - ondemand_price_snapshots: 30 days
    - risk_scores: 90 days
    - decision_engine_log: 30 days

    Process:
    - Delete records older than retention period from each table
    - Log cleanup completion
    - Create system event for audit trail

    Schedule: Daily at 2:00 AM

    Note: This job does not clean up core operational data like
    clients, instances, agents, or switches - only time-series
    snapshots and logs.
    """
    try:
        logger.info("Starting data cleanup...")

        # Import here to avoid circular imports
        from backend.backend import log_system_event

        # Clean spot price snapshots (30 days)
        execute_query("""
            DELETE FROM spot_price_snapshots
            WHERE captured_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)

        # Clean on-demand price snapshots (30 days)
        execute_query("""
            DELETE FROM ondemand_price_snapshots
            WHERE captured_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)

        # Clean risk scores (90 days)
        execute_query("""
            DELETE FROM risk_scores
            WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY)
        """)

        # Clean decision engine logs (30 days)
        execute_query("""
            DELETE FROM decision_engine_log
            WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)

        logger.info("✓ Old data cleaned up successfully")
        log_system_event('data_cleanup', 'info', 'Cleaned up old time-series data')

    except Exception as e:
        logger.error(f"Data cleanup job failed: {e}")

        # Import here to avoid circular imports
        from backend.backend import log_system_event
        log_system_event('cleanup_failed', 'error', str(e))

        raise


def register_jobs(scheduler):
    """
    Register data cleanup jobs with the scheduler.

    Args:
        scheduler: APScheduler BackgroundScheduler instance

    Jobs registered:
    - Daily cleanup: Runs daily at 2:00 AM
    """
    # Data cleanup (daily at 2:00 AM)
    scheduler.add_job(
        cleanup_old_data,
        'cron',
        hour=2,
        minute=0,
        id='cleanup_old_data',
        name='Daily data cleanup',
        replace_existing=True
    )
    logger.info("✓ Registered daily data cleanup job (2:00 AM)")
