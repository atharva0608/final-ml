"""
AWS Spot Optimizer - Pricing Data Aggregator Job
================================================
Deduplicates pricing data and fills gaps in time-series data
"""

import logging
from datetime import datetime, timedelta

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


def aggregate_pricing_hourly():
    """
    Run hourly deduplication of pricing submissions.

    This job processes raw pricing submissions from the last hour,
    identifies duplicates, and creates clean pricing snapshots.

    Process:
    - Get all raw submissions from the last hour
    - Identify duplicates based on pool_id, time_bucket, and price
    - Mark duplicates in the raw submissions table
    - Create or update clean pricing snapshots
    - Track processing statistics in data_processing_jobs table

    Schedule: Hourly
    Processing window: Last 1 hour

    Returns:
        dict: Processing statistics including processed count, duplicates found,
              new snapshots created, and replacements made
    """
    try:
        logger.info("Starting hourly pricing deduplication...")

        # Import here to avoid circular imports
        from backend.backend import deduplicate_batch

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        stats = deduplicate_batch(start_time, end_time)

        logger.info(f"✓ Hourly deduplication completed: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Hourly deduplication job failed: {e}")
        raise


def aggregate_pricing_daily():
    """
    Run daily gap-filling for all active spot pools.

    This job detects and fills gaps in pricing data time-series for all
    available spot pools using interpolation strategies.

    Process:
    - Query all active spot pools
    - For each pool, detect missing 5-minute time buckets
    - Fill gaps using appropriate interpolation:
      * Short gaps (≤2 buckets): Linear interpolation
      * Medium gaps (3-6 buckets): Weighted average
      * Long gaps (>6 buckets): Conservative (max of boundaries)
    - Track gap-filling metadata (method, confidence, gap type)

    Schedule: Daily
    Processing window: Last 24 hours

    Returns:
        dict: Aggregated statistics including total gaps found, gaps filled,
              and interpolations created across all pools
    """
    try:
        logger.info("Starting daily gap filling...")

        # Import here to avoid circular imports
        from backend.backend import detect_and_fill_gaps

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        pools = execute_query("""
            SELECT id FROM spot_pools WHERE is_available = TRUE
        """, fetch=True)

        total_stats = {
            'gaps_found': 0,
            'gaps_filled': 0,
            'interpolations_created': 0
        }

        for pool in (pools or []):
            try:
                stats = detect_and_fill_gaps(pool['id'], start_time, end_time)
                total_stats['gaps_found'] += stats.get('gaps_found', 0)
                total_stats['gaps_filled'] += stats.get('gaps_filled', 0)
                total_stats['interpolations_created'] += stats.get('interpolations_created', 0)
            except Exception as e:
                logger.error(f"Error filling gaps for pool {pool['id']}: {e}")

        logger.info(f"✓ Daily gap filling completed: {total_stats}")
        return total_stats

    except Exception as e:
        logger.error(f"Daily gap filling job failed: {e}")
        raise


def register_jobs(scheduler):
    """
    Register pricing aggregation jobs with the scheduler.

    Args:
        scheduler: APScheduler BackgroundScheduler instance

    Jobs registered:
    - Hourly deduplication: Runs every hour at minute 10
    - Daily gap filling: Runs daily at 3:00 AM
    """
    # Hourly deduplication (every hour at :10)
    scheduler.add_job(
        aggregate_pricing_hourly,
        'cron',
        hour='*',
        minute=10,
        id='aggregate_pricing_hourly',
        name='Hourly pricing deduplication',
        replace_existing=True
    )
    logger.info("✓ Registered hourly pricing deduplication job")

    # Daily gap filling (daily at 3:00 AM)
    scheduler.add_job(
        aggregate_pricing_daily,
        'cron',
        hour=3,
        minute=0,
        id='aggregate_pricing_daily',
        name='Daily pricing gap filling',
        replace_existing=True
    )
    logger.info("✓ Registered daily pricing gap filling job")
