"""
AWS Spot Optimizer - Admin Service
===================================
Business logic for administrative operations
"""

import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from backend.database_manager import execute_query
from backend.utils import generate_uuid, generate_client_id, generate_client_token, log_system_event

logger = logging.getLogger(__name__)


def create_client(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create new client"""
    name = data.get('name')
    email = data.get('email')

    if not name or not email:
        raise ValueError('Name and email are required')

    # Generate client ID and token
    client_id = generate_client_id()
    client_token = generate_client_token()

    # Insert client
    execute_query("""
        INSERT INTO clients (id, name, email, client_token, is_active)
        VALUES (%s, %s, %s, %s, TRUE)
    """, (client_id, name, email, client_token))

    log_system_event('client_created', 'info',
                    f"Client {name} created with ID {client_id}")

    logger.info(f"Client created: {client_id} ({name})")

    return {
        'client_id': client_id,
        'name': name,
        'email': email,
        'client_token': client_token,
        'is_active': True
    }


def delete_client(client_id: str) -> Dict[str, Any]:
    """Delete client"""
    # Mark client as inactive
    execute_query("""
        UPDATE clients
        SET is_active = FALSE
        WHERE id = %s
    """, (client_id,))

    # Mark all agents as deleted
    execute_query("""
        UPDATE agents
        SET status = 'deleted', enabled = FALSE
        WHERE client_id = %s
    """, (client_id,))

    log_system_event('client_deleted', 'warning',
                    f"Client {client_id} deleted")

    logger.warning(f"Client deleted: {client_id}")

    return {'success': True}


def regenerate_client_token(client_id: str) -> Dict[str, Any]:
    """Regenerate client token"""
    new_token = generate_client_token()

    execute_query("""
        UPDATE clients
        SET client_token = %s
        WHERE id = %s
    """, (new_token, client_id))

    log_system_event('token_regenerated', 'warning',
                    f"Token regenerated for client {client_id}",
                    client_id)

    logger.warning(f"Token regenerated for client: {client_id}")

    return {
        'client_id': client_id,
        'new_token': new_token
    }


def get_client_token(client_id: str) -> Dict[str, Any]:
    """Get client token"""
    client = execute_query("""
        SELECT client_token
        FROM clients
        WHERE id = %s
    """, (client_id,), fetch_one=True)

    if not client:
        raise ValueError('Client not found')

    return {'client_token': client['client_token']}


def get_admin_stats() -> Dict[str, Any]:
    """Get admin dashboard statistics"""
    # Total clients
    total_clients = execute_query("""
        SELECT COUNT(*) as count FROM clients WHERE is_active = TRUE
    """, fetch_one=True)

    # Total agents
    total_agents = execute_query("""
        SELECT COUNT(*) as count FROM agents WHERE status != 'deleted'
    """, fetch_one=True)

    # Online agents
    online_agents = execute_query("""
        SELECT COUNT(*) as count FROM agents
        WHERE status = 'online'
          AND last_heartbeat_at >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
    """, fetch_one=True)

    # Total instances
    total_instances = execute_query("""
        SELECT COUNT(*) as count FROM instances WHERE is_active = TRUE
    """, fetch_one=True)

    # Total savings
    total_savings = execute_query("""
        SELECT SUM(total_savings) as savings FROM clients WHERE is_active = TRUE
    """, fetch_one=True)

    # Switches today
    switches_today = execute_query("""
        SELECT COUNT(*) as count FROM switches
        WHERE initiated_at >= CURDATE()
    """, fetch_one=True)

    return {
        'total_clients': total_clients['count'] if total_clients else 0,
        'total_agents': total_agents['count'] if total_agents else 0,
        'online_agents': online_agents['count'] if online_agents else 0,
        'total_instances': total_instances['count'] if total_instances else 0,
        'total_savings': float(total_savings['savings']) if total_savings and total_savings['savings'] else 0,
        'switches_today': switches_today['count'] if switches_today else 0
    }


def get_all_clients() -> List[Dict[str, Any]]:
    """Get all clients"""
    clients = execute_query("""
        SELECT
            c.id,
            c.name,
            c.email,
            c.is_active,
            c.total_savings,
            c.created_at,
            COUNT(DISTINCT a.id) as agent_count,
            COUNT(DISTINCT i.id) as instance_count
        FROM clients c
        LEFT JOIN agents a ON c.id = a.client_id AND a.status != 'deleted'
        LEFT JOIN instances i ON c.id = i.client_id AND i.is_active = TRUE
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """, fetch=True)

    return clients or []


def get_client_growth(days: int = 30) -> List[Dict[str, Any]]:
    """Get client growth statistics"""
    growth = execute_query("""
        SELECT
            DATE(created_at) as date,
            COUNT(*) as new_clients
        FROM clients
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """, (days,), fetch=True)

    return growth or []


def get_all_instances() -> List[Dict[str, Any]]:
    """Get all instances across all clients"""
    instances = execute_query("""
        SELECT
            i.*,
            a.logical_agent_id,
            c.name as client_name,
            c.email as client_email
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        JOIN clients c ON i.client_id = c.id
        WHERE i.is_active = TRUE
        ORDER BY i.installed_at DESC
    """, fetch=True)

    return instances or []


def get_all_agents() -> List[Dict[str, Any]]:
    """Get all agents across all clients"""
    agents = execute_query("""
        SELECT
            a.*,
            c.name as client_name,
            c.email as client_email,
            i.instance_type,
            i.current_mode,
            TIMESTAMPDIFF(SECOND, a.last_heartbeat_at, NOW()) as seconds_since_heartbeat
        FROM agents a
        JOIN clients c ON a.client_id = c.id
        LEFT JOIN instances i ON a.instance_id = i.id
        WHERE a.status != 'deleted'
        ORDER BY a.last_heartbeat_at DESC
    """, fetch=True)

    return agents or []


def get_system_activity(days: int = 7) -> List[Dict[str, Any]]:
    """Get system activity log"""
    activity = execute_query("""
        SELECT *
        FROM system_events
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY created_at DESC
        LIMIT 100
    """, (days,), fetch=True)

    return activity or []


def get_system_health() -> Dict[str, Any]:
    """Get system health metrics"""
    # Database status
    db_status = execute_query("SELECT 1 as ok", fetch_one=True)

    # Stale agents (no heartbeat in 10 minutes)
    stale_agents = execute_query("""
        SELECT COUNT(*) as count
        FROM agents
        WHERE status = 'online'
          AND last_heartbeat_at < DATE_SUB(NOW(), INTERVAL 10 MINUTE)
    """, fetch_one=True)

    # Failed replicas
    failed_replicas = execute_query("""
        SELECT COUNT(*) as count
        FROM replica_instances
        WHERE status = 'failed'
          AND created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    """, fetch_one=True)

    # Recent errors
    recent_errors = execute_query("""
        SELECT COUNT(*) as count
        FROM system_events
        WHERE severity = 'error'
          AND created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
    """, fetch_one=True)

    return {
        'database': 'ok' if db_status else 'error',
        'stale_agents': stale_agents['count'] if stale_agents else 0,
        'failed_replicas': failed_replicas['count'] if failed_replicas else 0,
        'recent_errors': recent_errors['count'] if recent_errors else 0,
        'timestamp': datetime.utcnow().isoformat()
    }
