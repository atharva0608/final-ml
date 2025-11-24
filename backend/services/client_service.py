"""
AWS Spot Optimizer - Client Service
====================================
Business logic for client management
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from backend.database_manager import execute_query
from backend.utils import generate_uuid, generate_client_id, generate_client_token, log_system_event

logger = logging.getLogger(__name__)


def get_client_info(client_id: str) -> Dict[str, Any]:
    """Get client information"""
    client = execute_query("""
        SELECT
            id,
            name,
            email,
            is_active,
            total_savings,
            created_at
        FROM clients
        WHERE id = %s
    """, (client_id,), fetch_one=True)

    if not client:
        raise ValueError('Client not found')

    # Get agent count
    agent_count = execute_query("""
        SELECT COUNT(*) as count
        FROM agents
        WHERE client_id = %s
    """, (client_id,), fetch_one=True)

    # Get instance count
    instance_count = execute_query("""
        SELECT COUNT(*) as count
        FROM instances
        WHERE client_id = %s AND is_active = TRUE
    """, (client_id,), fetch_one=True)

    return {
        **client,
        'agent_count': agent_count['count'] if agent_count else 0,
        'instance_count': instance_count['count'] if instance_count else 0,
        'total_savings': float(client.get('total_savings', 0))
    }


def get_client_agents(client_id: str) -> List[Dict[str, Any]]:
    """Get all agents for client"""
    agents = execute_query("""
        SELECT
            a.*,
            i.instance_type,
            i.region,
            i.current_mode,
            i.spot_price,
            i.ondemand_price,
            TIMESTAMPDIFF(SECOND, a.last_heartbeat_at, NOW()) as seconds_since_heartbeat
        FROM agents a
        LEFT JOIN instances i ON a.instance_id = i.id
        WHERE a.client_id = %s
        ORDER BY a.created_at DESC
    """, (client_id,), fetch=True)

    return agents or []


def get_agent_decisions(client_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Get recent decisions for client's agents"""
    decisions = execute_query("""
        SELECT
            adh.*,
            a.logical_agent_id
        FROM agent_decision_history adh
        JOIN agents a ON adh.agent_id = a.id
        WHERE adh.client_id = %s
          AND adh.decision_time >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY adh.decision_time DESC
        LIMIT 100
    """, (client_id, days), fetch=True)

    return decisions or []


def toggle_agent_enabled(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle agent enabled status"""
    enabled = data.get('enabled', False)

    execute_query("""
        UPDATE agents
        SET enabled = %s
        WHERE id = %s AND client_id = %s
    """, (enabled, agent_id, client_id))

    logger.info(f"Agent {agent_id} enabled status changed to {enabled}")

    return {'success': True, 'enabled': enabled}


def update_agent_settings(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update agent settings"""
    auto_switch_enabled = data.get('auto_switch_enabled')
    auto_terminate_enabled = data.get('auto_terminate_enabled')
    replica_enabled = data.get('replica_enabled')

    # Build dynamic update query
    updates = []
    params = []

    if auto_switch_enabled is not None:
        updates.append("auto_switch_enabled = %s")
        params.append(auto_switch_enabled)

    if auto_terminate_enabled is not None:
        updates.append("auto_terminate_enabled = %s")
        params.append(auto_terminate_enabled)

    if replica_enabled is not None:
        updates.append("replica_enabled = %s")
        params.append(replica_enabled)

    if not updates:
        raise ValueError('No settings provided')

    params.extend([agent_id, client_id])

    execute_query(f"""
        UPDATE agents
        SET {', '.join(updates)}
        WHERE id = %s AND client_id = %s
    """, tuple(params))

    logger.info(f"Agent {agent_id} settings updated")

    return {'success': True}


def update_agent_config(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update agent configuration"""
    min_savings_percent = data.get('min_savings_percent')
    risk_threshold = data.get('risk_threshold')
    max_switches_per_week = data.get('max_switches_per_week')
    min_pool_duration_hours = data.get('min_pool_duration_hours')

    # Verify agent belongs to client
    agent = execute_query("""
        SELECT id FROM agents WHERE id = %s AND client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not agent:
        raise ValueError('Agent not found')

    # Check if config exists
    config_exists = execute_query("""
        SELECT agent_id FROM agent_configs WHERE agent_id = %s
    """, (agent_id,), fetch_one=True)

    if config_exists:
        # Build dynamic update
        updates = []
        params = []

        if min_savings_percent is not None:
            updates.append("min_savings_percent = %s")
            params.append(min_savings_percent)

        if risk_threshold is not None:
            updates.append("risk_threshold = %s")
            params.append(risk_threshold)

        if max_switches_per_week is not None:
            updates.append("max_switches_per_week = %s")
            params.append(max_switches_per_week)

        if min_pool_duration_hours is not None:
            updates.append("min_pool_duration_hours = %s")
            params.append(min_pool_duration_hours)

        if updates:
            params.append(agent_id)
            execute_query(f"""
                UPDATE agent_configs
                SET {', '.join(updates)}
                WHERE agent_id = %s
            """, tuple(params))
    else:
        # Insert new config
        execute_query("""
            INSERT INTO agent_configs (
                agent_id, min_savings_percent, risk_threshold,
                max_switches_per_week, min_pool_duration_hours
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            agent_id,
            min_savings_percent,
            risk_threshold,
            max_switches_per_week,
            min_pool_duration_hours
        ))

    logger.info(f"Agent {agent_id} config updated")

    return {'success': True}


def delete_agent(agent_id: str, client_id: str) -> Dict[str, Any]:
    """Delete agent"""
    # Verify agent belongs to client
    agent = execute_query("""
        SELECT id, logical_agent_id FROM agents
        WHERE id = %s AND client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not agent:
        raise ValueError('Agent not found')

    # Mark agent as deleted
    execute_query("""
        UPDATE agents
        SET status = 'deleted', enabled = FALSE
        WHERE id = %s
    """, (agent_id,))

    # Mark instances as inactive
    execute_query("""
        UPDATE instances
        SET is_active = FALSE
        WHERE agent_id = %s
    """, (agent_id,))

    log_system_event('agent_deleted', 'info',
                    f"Agent {agent['logical_agent_id']} deleted",
                    client_id, agent_id)

    logger.info(f"Agent {agent_id} deleted")

    return {'success': True}


def get_agent_history(client_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get agent activity history"""
    history = execute_query("""
        SELECT
            a.id,
            a.logical_agent_id,
            a.status,
            a.created_at,
            a.last_heartbeat_at,
            COUNT(DISTINCT s.id) as switch_count,
            SUM(s.savings_impact) as total_savings
        FROM agents a
        LEFT JOIN switches s ON a.id = s.agent_id
            AND s.initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        WHERE a.client_id = %s
        GROUP BY a.id
        ORDER BY a.created_at DESC
    """, (days, client_id), fetch=True)

    return history or []


def get_client_replicas(client_id: str) -> List[Dict[str, Any]]:
    """Get all replicas for client"""
    replicas = execute_query("""
        SELECT
            ri.*,
            a.logical_agent_id,
            sp.az,
            sp.region
        FROM replica_instances ri
        JOIN agents a ON ri.agent_id = a.id
        JOIN spot_pools sp ON ri.pool_id = sp.id
        WHERE a.client_id = %s
          AND ri.status IN ('launching', 'syncing', 'ready')
        ORDER BY ri.created_at DESC
    """, (client_id,), fetch=True)

    return replicas or []


def get_client_savings(client_id: str, days: int = 30) -> Dict[str, Any]:
    """Get savings statistics for client"""
    savings = execute_query("""
        SELECT
            SUM(savings_impact) as total_savings,
            COUNT(*) as switch_count,
            AVG(savings_impact) as avg_savings_per_switch
        FROM switches
        WHERE client_id = %s
          AND initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
    """, (client_id, days), fetch_one=True)

    # Get current hourly savings
    current_savings = execute_query("""
        SELECT
            SUM(i.ondemand_price - i.spot_price) as hourly_savings
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        WHERE i.client_id = %s
          AND i.is_active = TRUE
          AND i.current_mode = 'spot'
    """, (client_id,), fetch_one=True)

    return {
        'total_savings': float(savings.get('total_savings', 0)) if savings else 0,
        'switch_count': savings.get('switch_count', 0) if savings else 0,
        'avg_savings_per_switch': float(savings.get('avg_savings_per_switch', 0)) if savings else 0,
        'current_hourly_savings': float(current_savings.get('hourly_savings', 0)) if current_savings else 0,
        'projected_monthly_savings': float(current_savings.get('hourly_savings', 0)) * 730 if current_savings else 0,
        'days': days
    }


def get_switch_history(client_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get switch history for client"""
    history = execute_query("""
        SELECT
            s.*,
            a.logical_agent_id
        FROM switches s
        JOIN agents a ON s.agent_id = a.id
        WHERE s.client_id = %s
          AND s.initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY s.initiated_at DESC
        LIMIT 100
    """, (client_id, days), fetch=True)

    return history or []


def get_chart_stats(client_id: str, days: int = 30) -> Dict[str, Any]:
    """Get chart statistics for client"""
    # Daily savings
    daily_savings = execute_query("""
        SELECT
            DATE(initiated_at) as date,
            SUM(savings_impact) as savings,
            COUNT(*) as switches
        FROM switches
        WHERE client_id = %s
          AND initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY DATE(initiated_at)
        ORDER BY date ASC
    """, (client_id, days), fetch=True)

    # Agent distribution
    agent_distribution = execute_query("""
        SELECT
            current_mode,
            COUNT(*) as count
        FROM agents
        WHERE client_id = %s
          AND status = 'online'
        GROUP BY current_mode
    """, (client_id,), fetch=True)

    # Switch triggers
    switch_triggers = execute_query("""
        SELECT
            event_trigger,
            COUNT(*) as count
        FROM switches
        WHERE client_id = %s
          AND initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY event_trigger
    """, (client_id, days), fetch=True)

    return {
        'daily_savings': daily_savings or [],
        'agent_distribution': agent_distribution or [],
        'switch_triggers': switch_triggers or []
    }
