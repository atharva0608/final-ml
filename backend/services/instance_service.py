"""
AWS Spot Optimizer - Instance Service
======================================
Business logic for instance management
"""

import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from backend.database_manager import execute_query
from backend.utils import log_system_event

logger = logging.getLogger(__name__)


def get_instance_pricing(instance_id: str, client_id: str) -> Dict[str, Any]:
    """Get pricing information for instance"""
    instance = execute_query("""
        SELECT
            i.*,
            a.logical_agent_id
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        WHERE i.id = %s AND i.client_id = %s
    """, (instance_id, client_id), fetch_one=True)

    if not instance:
        raise ValueError('Instance not found')

    # Get latest pricing
    latest_pricing = execute_query("""
        SELECT *
        FROM pricing_reports
        WHERE instance_id = %s
        ORDER BY collected_at DESC
        LIMIT 1
    """, (instance_id,), fetch_one=True)

    return {
        'instance': instance,
        'latest_pricing': latest_pricing,
        'spot_price': float(instance.get('spot_price', 0)),
        'ondemand_price': float(instance.get('ondemand_price', 0)),
        'savings_percent': ((instance.get('ondemand_price', 0) - instance.get('spot_price', 0)) /
                           instance.get('ondemand_price', 1)) * 100 if instance.get('ondemand_price') else 0
    }


def get_instance_metrics(instance_id: str, client_id: str, days: int = 7) -> Dict[str, Any]:
    """Get metrics for instance"""
    # Get switch count
    switch_count = execute_query("""
        SELECT COUNT(*) as count
        FROM switches
        WHERE (old_instance_id = %s OR new_instance_id = %s)
          AND client_id = %s
          AND initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
    """, (instance_id, instance_id, client_id, days), fetch_one=True)

    # Get uptime
    instance = execute_query("""
        SELECT installed_at, terminated_at
        FROM instances
        WHERE id = %s AND client_id = %s
    """, (instance_id, client_id), fetch_one=True)

    if not instance:
        raise ValueError('Instance not found')

    uptime_hours = 0
    if instance['installed_at']:
        end_time = instance['terminated_at'] or datetime.utcnow()
        uptime_hours = (end_time - instance['installed_at']).total_seconds() / 3600

    return {
        'switch_count': switch_count['count'] if switch_count else 0,
        'uptime_hours': round(uptime_hours, 2),
        'days': days
    }


def get_price_history(instance_id: str, client_id: str, days: int = 7) -> Dict[str, Any]:
    """Get price history for instance"""
    history = execute_query("""
        SELECT
            current_spot_price,
            on_demand_price,
            collected_at
        FROM pricing_reports
        WHERE instance_id = %s
          AND collected_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY collected_at ASC
    """, (instance_id, days), fetch=True)

    return {
        'history': history or [],
        'data_points': len(history or []),
        'days': days
    }


def get_available_options(instance_id: str, client_id: str) -> Dict[str, Any]:
    """Get available switch options for instance"""
    instance = execute_query("""
        SELECT
            i.*,
            a.instance_type,
            a.region
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        WHERE i.id = %s AND i.client_id = %s
    """, (instance_id, client_id), fetch_one=True)

    if not instance:
        raise ValueError('Instance not found')

    # Get available pools
    pools = execute_query("""
        SELECT
            sp.id as pool_id,
            sp.az,
            sp.instance_type,
            sp.region,
            COALESCE(latest.price, 0) as current_price
        FROM spot_pools sp
        LEFT JOIN (
            SELECT pool_id, price
            FROM spot_price_snapshots
            WHERE (pool_id, captured_at) IN (
                SELECT pool_id, MAX(captured_at)
                FROM spot_price_snapshots
                GROUP BY pool_id
            )
        ) latest ON sp.id = latest.pool_id
        WHERE sp.instance_type = %s
          AND sp.region = %s
          AND sp.id != %s
        ORDER BY latest.price ASC
    """, (instance['instance_type'], instance['region'], instance.get('current_pool_id')), fetch=True)

    return {
        'current_mode': instance.get('current_mode'),
        'current_pool_id': instance.get('current_pool_id'),
        'available_pools': pools or [],
        'can_switch_to_ondemand': instance.get('current_mode') != 'ondemand'
    }


def get_client_instances(client_id: str) -> List[Dict[str, Any]]:
    """Get all instances for client"""
    instances = execute_query("""
        SELECT
            i.*,
            a.logical_agent_id,
            a.status as agent_status,
            a.last_heartbeat_at
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        WHERE i.client_id = %s
          AND i.is_active = TRUE
        ORDER BY i.installed_at DESC
    """, (client_id,), fetch=True)

    return instances or []
