"""
AWS Spot Optimizer - Snapshot Jobs
===================================
Client growth snapshots and monthly savings calculations
"""

import logging
from datetime import datetime

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


def snapshot_client_growth():
    """
    Take daily snapshot of client counts for growth analytics.

    This job runs daily to capture client growth metrics for
    dashboard analytics and reporting.

    Metrics captured:
    - total_clients: Total number of clients in the system
    - new_clients_today: New clients added since last snapshot
    - active_clients: Currently active clients

    Process:
    - Count total clients in database
    - Compare with yesterday's snapshot to calculate new clients
    - Insert or update today's snapshot with ON DUPLICATE KEY
    - Log snapshot results

    Schedule: Daily at 12:05 AM

    Note: The snapshot_date field has a UNIQUE constraint, so this
    job is idempotent and can be safely re-run on the same day.
    """
    try:
        logger.info("Taking daily client snapshot...")

        # Get current counts (all clients, no is_active filter)
        today_count = execute_query(
            "SELECT COUNT(*) as cnt FROM clients",
            fetch_one=True
        )
        total_clients = today_count['cnt'] if today_count else 0

        # Get yesterday's count to calculate new clients
        yesterday_row = execute_query("""
            SELECT total_clients FROM clients_daily_snapshot
            ORDER BY snapshot_date DESC LIMIT 1
        """, fetch_one=True)
        yesterday_count = yesterday_row['total_clients'] if yesterday_row else 0

        new_clients_today = total_clients - yesterday_count if yesterday_count else total_clients

        # Insert today's snapshot
        execute_query("""
            INSERT INTO clients_daily_snapshot
            (snapshot_date, total_clients, new_clients_today, active_clients)
            VALUES (CURDATE(), %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_clients=%s,
                new_clients_today=%s,
                active_clients=%s
        """, (total_clients, new_clients_today, total_clients,
              total_clients, new_clients_today, total_clients))

        logger.info(f"✓ Daily snapshot: {total_clients} total, {new_clients_today} new")

    except Exception as e:
        logger.error(f"Daily snapshot error: {e}")
        raise


def calculate_monthly_savings():
    """
    Compute monthly savings for all active clients.

    This job calculates cost savings for each client by comparing
    baseline on-demand costs with actual costs from spot usage.

    Calculation methodology:
    - Baseline cost: Sum of all instances at on-demand prices
    - Actual cost: Sum of costs from switch events (spot vs on-demand)
    - Savings: Baseline cost - Actual cost

    Process:
    - For each active client:
      * Calculate baseline on-demand cost (instances * on-demand price * hours)
      * Calculate actual cost from switches table (considers spot/on-demand mode)
      * Compute savings (always >= 0)
      * Store in client_savings_monthly table
    - Use ON DUPLICATE KEY UPDATE for idempotency
    - Log results and system events

    Schedule: Daily at 1:00 AM

    Note: Runs daily but computes for current month, so month-to-date
    savings are updated daily. Final monthly values are locked when
    the month rolls over.
    """
    try:
        logger.info("Starting monthly savings computation...")

        # Import here to avoid circular imports
        from backend.backend import log_system_event

        clients = execute_query(
            "SELECT id FROM clients WHERE is_active = TRUE",
            fetch=True
        )

        now = datetime.utcnow()
        year = now.year
        month = now.month

        for client in (clients or []):
            try:
                # Calculate baseline (on-demand) cost
                baseline = execute_query("""
                    SELECT SUM(baseline_ondemand_price * 24 * 30) as cost
                    FROM instances
                    WHERE client_id = %s AND is_active = TRUE
                """, (client['id'],), fetch_one=True)

                # Calculate actual cost from switch events
                actual = execute_query("""
                    SELECT
                        SUM(CASE
                            WHEN new_mode = 'spot' THEN new_spot_price * 24 * 30
                            ELSE on_demand_price * 24 * 30
                        END) as cost
                    FROM switches
                    WHERE client_id = %s
                    AND YEAR(initiated_at) = %s
                    AND MONTH(initiated_at) = %s
                """, (client['id'], year, month), fetch_one=True)

                baseline_cost = float(baseline['cost'] or 0)
                actual_cost = float(actual['cost'] or 0) if actual else baseline_cost
                savings = max(0, baseline_cost - actual_cost)

                # Store monthly savings
                execute_query("""
                    INSERT INTO client_savings_monthly
                    (client_id, year, month, baseline_cost, actual_cost, savings)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        baseline_cost = VALUES(baseline_cost),
                        actual_cost = VALUES(actual_cost),
                        savings = VALUES(savings),
                        computed_at = NOW()
                """, (client['id'], year, month, baseline_cost, actual_cost, savings))

            except Exception as e:
                logger.error(f"Failed to compute savings for client {client['id']}: {e}")

        logger.info(f"✓ Monthly savings computed for {len(clients or [])} clients")
        log_system_event(
            'savings_computed',
            'info',
            f"Computed monthly savings for {len(clients or [])} clients"
        )

    except Exception as e:
        logger.error(f"Savings computation job failed: {e}")

        # Import here to avoid circular imports
        from backend.backend import log_system_event
        log_system_event('savings_computation_failed', 'error', str(e))

        raise


def register_jobs(scheduler):
    """
    Register snapshot and savings jobs with the scheduler.

    Args:
        scheduler: APScheduler BackgroundScheduler instance

    Jobs registered:
    - Daily client snapshot: Runs daily at 12:05 AM
    - Monthly savings computation: Runs daily at 1:00 AM
    """
    # Daily client snapshot (daily at 12:05 AM)
    scheduler.add_job(
        snapshot_client_growth,
        'cron',
        hour=0,
        minute=5,
        id='snapshot_client_growth',
        name='Daily client growth snapshot',
        replace_existing=True
    )
    logger.info("✓ Registered daily client snapshot job (12:05 AM)")

    # Monthly savings computation (daily at 1:00 AM)
    scheduler.add_job(
        calculate_monthly_savings,
        'cron',
        hour=1,
        minute=0,
        id='calculate_monthly_savings',
        name='Monthly savings computation',
        replace_existing=True
    )
    logger.info("✓ Registered monthly savings computation job (1:00 AM)")
