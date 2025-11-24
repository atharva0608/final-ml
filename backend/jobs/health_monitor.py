"""
AWS Spot Optimizer - Agent Health Monitor Job
==============================================
Monitors agent health and marks stale agents as offline
"""

import logging
from datetime import datetime

from backend.database_manager import execute_query
from backend.config import app_config

logger = logging.getLogger(__name__)


def mark_stale_agents_offline():
    """
    Check agent health and mark stale agents as offline.

    This job runs every 5 minutes to ensure agents that haven't sent
    heartbeats within the timeout period are marked as offline.

    Process:
    - Query for agents marked 'online' but with stale heartbeats
    - Update their status to 'offline'
    - Create client notifications for each offline agent
    - Log system events for tracking

    Configuration:
    - Timeout threshold: config.AGENT_HEARTBEAT_TIMEOUT (default: 120 seconds)
    - Schedule: Every 5 minutes
    """
    try:
        timeout = app_config.AGENT_HEARTBEAT_TIMEOUT

        stale_agents = execute_query(f"""
            SELECT id, client_id, instance_id, hostname, last_heartbeat_at
            FROM agents
            WHERE status = 'online'
            AND last_heartbeat_at < DATE_SUB(NOW(), INTERVAL {timeout} SECOND)
        """, fetch=True)

        for agent in (stale_agents or []):
            execute_query("""
                UPDATE agents SET status = 'offline' WHERE id = %s
            """, (agent['id'],))

            # Import here to avoid circular imports
            from backend.backend import create_notification, log_system_event

            # Create notification for client
            create_notification(
                f"Agent {agent['hostname'] or agent['id']} marked offline (heartbeat timeout)",
                'warning',
                agent['client_id']
            )

            # Log system event for tracking
            log_system_event(
                'agent_marked_offline',
                'warning',
                f"Agent {agent['hostname'] or agent['id']} marked offline due to heartbeat timeout ({timeout}s)",
                agent['client_id'],
                agent['id'],
                agent['instance_id'],
                metadata={
                    'timeout_seconds': timeout,
                    'last_heartbeat_at': agent['last_heartbeat_at'].isoformat() if agent['last_heartbeat_at'] else None
                }
            )

        if stale_agents:
            logger.info(f"Marked {len(stale_agents)} stale agents as offline")

    except Exception as e:
        logger.error(f"Agent health check job failed: {e}")


def register_jobs(scheduler):
    """
    Register health monitor jobs with the scheduler.

    Args:
        scheduler: APScheduler BackgroundScheduler instance
    """
    # Agent health check (every 5 minutes)
    scheduler.add_job(
        mark_stale_agents_offline,
        'interval',
        minutes=5,
        id='mark_stale_agents_offline',
        name='Mark stale agents as offline',
        replace_existing=True
    )
    logger.info("✓ Registered agent health monitor job (every 5 minutes)")
