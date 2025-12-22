"""
Job Scheduler

Manages background jobs using APScheduler.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import atexit

from database.connection import SessionLocal
from database.models import Account
from .cleanup import cleanup_expired_sessions, cleanup_old_experiment_logs, update_session_counts
from .waste_scanner import WasteScanner
from .security_enforcer import SecurityEnforcer

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

    # Job 4: Waste Scanner (Daily at 6 AM)
    scheduler.add_job(
        func=run_waste_scanner,
        trigger=CronTrigger(hour=6, minute=0),
        id='run_waste_scanner',
        name='Run Waste Scanner',
        replace_existing=True
    )

    # Job 5: Security Enforcer (Every 30 minutes)
    scheduler.add_job(
        func=run_security_enforcer,
        trigger=IntervalTrigger(minutes=30),
        id='run_security_enforcer',
        name='Run Security Enforcer',
        replace_existing=True
    )

    # Job 6: Cleanup False Rebalance Replicas (Every 1 hour)
    scheduler.add_job(
        func=run_replica_cleanup,
        trigger=IntervalTrigger(hours=1),
        id='cleanup_fake_rebalances',
        name='Cleanup False Rebalance Replicas',
        replace_existing=True
    )

    scheduler.start()

    print("✓ Background scheduler started")
    print("  Jobs scheduled:")
    print("    - Cleanup expired sessions (every 5 minutes)")
    print("    - Update session counts (every 10 minutes)")
    print("    - Archive old logs (daily at 2 AM)")
    print("    - Waste Scanner (daily at 6 AM)")
    print("    - Security Enforcer (every 30 minutes)")
    print("    - Cleanup false rebalance replicas (every 1 hour)")

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


def run_waste_scanner():
    """Run waste scanner for all accounts"""
    db = SessionLocal()
    try:
        scanner = WasteScanner(db)
        accounts = db.query(Account).all()
        for account in accounts:
            try:
                scanner.scan_account(account.id, account.region)
            except Exception as e:
                print(f"Failed to scan account {account.account_id}: {e}")
    except Exception as e:
        print(f"Waste Scanner job failed: {e}")
    finally:
        db.close()


def run_security_enforcer():
    """Run security enforcer for all accounts"""
    db = SessionLocal()
    try:
        enforcer = SecurityEnforcer(db)
        accounts = db.query(Account).all()
        for account in accounts:
            try:
                # Run audit (auto-terminate=False by default for safety in background job)
                enforcer.audit_account(account.id, account.region, auto_terminate=False)
            except Exception as e:
                print(f"Failed to audit account {account.account_id}: {e}")
    except Exception as e:
        print(f"Security Enforcer job failed: {e}")
    finally:
        db.close()


def run_replica_cleanup():
    """
    Cleanup false rebalance replicas (runs every 1 hour)

    AWS sends 40% false rebalances (no termination follows).
    After 6hr without termination, replica is wasted cost.

    This job finds expired replicas and terminates them to save money.
    Savings: ~$10-50/month per false alarm
    """
    db = SessionLocal()
    try:
        from workers.event_processor import cleanup_fake_rebalances

        result = cleanup_fake_rebalances(db)

        if result['status'] == 'success' and result['replicas_cleaned'] > 0:
            print(
                f"✓ Replica cleanup: {result['replicas_cleaned']} false alarms removed, "
                f"${result['cost_saved_usd']:.2f} saved"
            )

    except Exception as e:
        print(f"Replica cleanup job failed: {e}")
    finally:
        db.close()
