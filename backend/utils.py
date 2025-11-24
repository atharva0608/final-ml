"""
AWS Spot Optimizer - Utility Functions Module
==============================================
Common utility functions used across the application
"""

import json
import logging
import secrets
import string
import uuid

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


def generate_uuid() -> str:
    """Generate UUID"""
    return str(uuid.uuid4())


def generate_client_token() -> str:
    """Generate a secure random client token"""
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(32))
    return f"token-{random_part}"


def generate_client_id() -> str:
    """Generate a unique client ID"""
    return f"client-{secrets.token_hex(4)}"


def log_system_event(event_type: str, severity: str, message: str,
                     client_id: str = None, agent_id: str = None,
                     instance_id: str = None, metadata: dict = None):
    """Log system event to database"""
    try:
        execute_query("""
            INSERT INTO system_events (event_type, severity, client_id, agent_id,
                                      instance_id, message, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (event_type, severity, client_id, agent_id, instance_id,
              message, json.dumps(metadata) if metadata else None))
    except Exception as e:
        logger.error(f"Failed to log system event: {e}")


def create_notification(message: str, severity: str = 'info', client_id: str = None):
    """Create a notification"""
    try:
        execute_query("""
            INSERT INTO notifications (id, message, severity, client_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (generate_uuid(), message, severity, client_id))
        logger.info(f"Notification created: {message[:50]}...")
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
