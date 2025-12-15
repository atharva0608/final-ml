"""
Cleanup Jobs

Background jobs for cleaning up expired sessions and resources.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import SandboxSession
from websocket.manager import manager


def cleanup_expired_sessions():
    """
    Background job to cleanup expired sandbox sessions

    This job runs periodically to:
    1. Mark expired sessions as inactive
    2. Clean up AWS resources (stop instances)
    3. Notify connected WebSocket clients

    Should be scheduled to run every 5 minutes.
    """
    db: Session = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print("🧹 CLEANUP JOB - Removing expired sessions")
        print("=" * 80)

        # Find expired sessions that are still marked as active
        now = datetime.utcnow()
        expired_sessions = db.query(SandboxSession).filter(
            SandboxSession.is_active == True,
            SandboxSession.expires_at <= now
        ).all()

        if not expired_sessions:
            print("  No expired sessions found")
            print("=" * 80 + "\n")
            return

        print(f"  Found {len(expired_sessions)} expired sessions")
        print()

        for session in expired_sessions:
            session_id = str(session.session_id)
            print(f"  🗑️  Cleaning up session: {session_id}")
            print(f"     User: {session.user_id}")
            print(f"     Instance: {session.target_instance_id}")
            print(f"     Expired at: {session.expires_at}")

            # Mark session as inactive
            session.is_active = False

            # TODO: Clean up AWS resources
            # 1. Stop spot instances launched during session
            # 2. Restart original instance
            # 3. Delete temporary AMIs
            # This would require:
            # - Decrypt AWS credentials from session.aws_access_key_encrypted
            # - Create boto3 client
            # - Query session.actions for created resources
            # - Stop/terminate/delete resources

            # Notify WebSocket clients
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.create_task(
                    manager.send_log(
                        session_id,
                        "SYSTEM",
                        "Session expired - cleaning up resources",
                        "WARNING"
                    )
                )
            except Exception as e:
                print(f"     Failed to send WebSocket notification: {e}")

            print(f"     ✓ Session marked as inactive")

        # Commit changes
        db.commit()

        print()
        print(f"  ✓ Cleaned up {len(expired_sessions)} sessions")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"  ❌ Cleanup job failed: {e}")
        db.rollback()
    finally:
        db.close()


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
