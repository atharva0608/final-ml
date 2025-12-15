"""
Job Scheduler

Manages background jobs using APScheduler.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import atexit

from .cleanup import cleanup_expired_sessions, cleanup_old_experiment_logs, update_session_counts

# Global scheduler instance
scheduler = None


def start_scheduler():
    """
    Start the background job scheduler

    This should be called on application startup.

    Jobs scheduled:
    - cleanup_expired_sessions: Every 5 minutes
    - update_session_counts: Every 10 minutes
    - cleanup_old_experiment_logs: Daily at 2 AM
    """
    global scheduler

    if scheduler is not None:
        print("⚠️  Scheduler already running")
        return

    scheduler = BackgroundScheduler()

    # Job 1: Cleanup expired sandbox sessions (every 5 minutes)
    scheduler.add_job(
        func=cleanup_expired_sessions,
        trigger=IntervalTrigger(minutes=5),
        id='cleanup_expired_sessions',
        name='Cleanup expired sandbox sessions',
        replace_existing=True
    )

    # Job 2: Update session counts for rate limiting (every 10 minutes)
    scheduler.add_job(
        func=update_session_counts,
        trigger=IntervalTrigger(minutes=10),
        id='update_session_counts',
        name='Update user session counts',
        replace_existing=True
    )

    # Job 3: Archive old experiment logs (daily at 2 AM)
    scheduler.add_job(
        func=cleanup_old_experiment_logs,
        trigger=CronTrigger(hour=2, minute=0),
        id='cleanup_old_logs',
        name='Archive old experiment logs',
        replace_existing=True
    )

    scheduler.start()

    print("✓ Background scheduler started")
    print("  Jobs scheduled:")
    print("    - Cleanup expired sessions (every 5 minutes)")
    print("    - Update session counts (every 10 minutes)")
    print("    - Archive old logs (daily at 2 AM)")

    # Shut down scheduler on exit
    atexit.register(stop_scheduler)


def stop_scheduler():
    """
    Stop the background job scheduler

    This should be called on application shutdown.
    """
    global scheduler

    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        print("✓ Background scheduler stopped")


def get_scheduler():
    """Get the scheduler instance"""
    return scheduler
