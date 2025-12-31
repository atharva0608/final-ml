"""
Cleanup Jobs

Background jobs for cleaning up expired sessions and resources.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
# from database.models import SandboxSession  # Not yet implemented
from websocket.manager import manager


def cleanup_expired_sessions():
    """
    Background job to cleanup expired sandbox sessions

    This job runs periodically to:
    1. Mark expired sessions as inactive
    2. Clean up AWS resources (stop instances)
    3. Notify connected WebSocket clients

    Should be scheduled to run every 5 minutes.

    TODO: Implement after SandboxSession model is created
    """
    pass  # Temporarily disabled - SandboxSession not yet implemented


def cleanup_old_experiment_logs(days: int = 90):
    """
    Background job to archive old experiment logs

    Args:
        days: Delete logs older than this many days
    """
    db: Session = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print(f"🧹 CLEANUP JOB - Archiving experiment logs older than {days} days")
        print("=" * 80)

        from datetime import timedelta
        from database.models import ExperimentLog

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Count old logs
        old_logs_count = db.query(ExperimentLog).filter(
            ExperimentLog.execution_time < cutoff_date
        ).count()

        if old_logs_count == 0:
            print("  No old logs to archive")
            print("=" * 80 + "\n")
            return

        print(f"  Found {old_logs_count} logs older than {cutoff_date}")

        # TODO: Export to S3 or data warehouse before deleting
        # For now, just delete
        db.query(ExperimentLog).filter(
            ExperimentLog.execution_time < cutoff_date
        ).delete()

        db.commit()

        print(f"  ✓ Archived {old_logs_count} logs")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"  ❌ Archive job failed: {e}")
        db.rollback()
    finally:
        db.close()


def update_session_counts():
    """
    Update active session counts for users (for rate limiting)
    """
    db: Session = SessionLocal()

    try:
        from database.models import User

        users = db.query(User).all()

        for user in users:
            active_count = db.query(SandboxSession).filter(
                SandboxSession.user_id == user.id,
                SandboxSession.is_active == True
            ).count()

            user.active_sessions_count = active_count

        db.commit()

    except Exception as e:
        print(f"Session count update failed: {e}")
        db.rollback()
    finally:
        db.close()
