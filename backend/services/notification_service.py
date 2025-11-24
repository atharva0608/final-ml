"""
AWS Spot Optimizer - Notification Service
==========================================
Business logic for notification management
"""

import logging
from typing import Dict, Any, List

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


def get_notifications(client_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get notifications for client"""
    notifications = execute_query("""
        SELECT *
        FROM notifications
        WHERE client_id = %s OR client_id IS NULL
        ORDER BY created_at DESC
        LIMIT %s
    """, (client_id, limit), fetch=True)

    return notifications or []


def mark_notification_read(notification_id: str, client_id: str) -> Dict[str, Any]:
    """Mark notification as read"""
    execute_query("""
        UPDATE notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE id = %s AND (client_id = %s OR client_id IS NULL)
    """, (notification_id, client_id))

    return {'success': True}


def mark_all_notifications_read(client_id: str) -> Dict[str, Any]:
    """Mark all notifications as read for client"""
    execute_query("""
        UPDATE notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE (client_id = %s OR client_id IS NULL) AND is_read = FALSE
    """, (client_id,))

    return {'success': True}
