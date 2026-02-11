"""
Approval Cleanup Worker
Marks expired approvals as EXPIRED
"""
from backend.workers.app import app
from backend.models.base import get_db
from backend.models.approval import Approval, ApprovalStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@app.task(name='workers.approval.cleanup_expired')
def cleanup_expired_approvals():
    """
    Mark approvals that have passed their expiration time as EXPIRED.
    Runs every 5 minutes.
    """
    db = next(get_db())
    try:
        now = datetime.utcnow()

        # Find all APPROVED_ACTIVE approvals that have expired
        expired_approvals = db.query(Approval).filter(
            Approval.status == ApprovalStatus.APPROVED_ACTIVE,
            Approval.expires_at <= now
        ).all()

        count = 0
        for approval in expired_approvals:
            approval.status = ApprovalStatus.EXPIRED
            count += 1
            logger.info(f"Marked approval {approval.id} as EXPIRED (expired at {approval.expires_at})")

        db.commit()

        if count > 0:
            logger.info(f"✅ Marked {count} expired approval(s) as EXPIRED")

        return {
            "expired_count": count,
            "timestamp": now.isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Approval cleanup failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
