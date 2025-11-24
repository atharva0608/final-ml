"""
AWS Spot Optimizer - Decision Service
======================================
Business logic for ML decision making and recommendations
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backend.database_manager import execute_query
from backend.utils import log_system_event

logger = logging.getLogger(__name__)


def make_decision(agent_id: str, client_id: str, data: Dict[str, Any], decision_engine_manager) -> Dict[str, Any]:
    """
    Get switching decision from decision engine

    Args:
        agent_id: Agent UUID
        client_id: Client ID for authorization
        data: Instance and pricing data
        decision_engine_manager: Decision engine manager instance

    Returns:
        Decision with recommendations
    """
    instance = data['instance']
    pricing = data['pricing']

    # Get agent config
    config_data = execute_query("""
        SELECT
            a.enabled,
            a.auto_switch_enabled,
            COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
            COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
            COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
            COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
        FROM agents a
        LEFT JOIN agent_configs ac ON ac.agent_id = a.id
        WHERE a.id = %s AND a.client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not config_data or not config_data['enabled']:
        return {
            'instance_id': instance.get('instance_id'),
            'risk_score': 0.0,
            'recommended_action': 'stay',
            'recommended_mode': instance.get('current_mode'),
            'recommended_pool_id': instance.get('current_pool_id'),
            'expected_savings_per_hour': 0.0,
            'allowed': False,
            'reason': 'Agent disabled'
        }

    # Get recent switches count
    recent_switches = execute_query("""
        SELECT COUNT(*) as count
        FROM switches
        WHERE agent_id = %s AND initiated_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """, (agent_id,), fetch_one=True)

    # Get last switch time
    last_switch = execute_query("""
        SELECT initiated_at FROM switches
        WHERE agent_id = %s
        ORDER BY initiated_at DESC
        LIMIT 1
    """, (agent_id,), fetch_one=True)

    # Make decision using ML engine
    decision = decision_engine_manager.make_decision(
        instance=instance,
        pricing=pricing,
        config_data=config_data,
        recent_switches_count=recent_switches['count'] if recent_switches else 0,
        last_switch_time=last_switch['initiated_at'] if last_switch else None
    )

    # Store decision in database
    execute_query("""
        INSERT INTO risk_scores (
            client_id, instance_id, agent_id, risk_score, recommended_action,
            recommended_pool_id, recommended_mode, expected_savings_per_hour,
            allowed, reason, model_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        client_id, instance.get('instance_id'), agent_id,
        decision.get('risk_score'), decision.get('recommended_action'),
        decision.get('recommended_pool_id'), decision.get('recommended_mode'),
        decision.get('expected_savings_per_hour'), decision.get('allowed'),
        decision.get('reason'), decision_engine_manager.engine_version
    ))

    # Log decision to history table for analytics
    try:
        execute_query("""
            INSERT INTO agent_decision_history (
                agent_id, client_id, decision_type, recommended_action,
                recommended_pool_id, risk_score, expected_savings,
                current_mode, current_pool_id, current_price, decision_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            agent_id, client_id,
            decision.get('recommended_action', 'stay'),
            decision.get('recommended_action'),
            decision.get('recommended_pool_id'),
            decision.get('risk_score', 0),
            decision.get('expected_savings_per_hour', 0),
            instance.get('current_mode'),
            instance.get('current_pool_id'),
            pricing.get('current_spot_price', 0)
        ))
    except Exception as log_error:
        logger.warning(f"Failed to log decision history: {log_error}")

    return decision


def get_switch_recommendation(agent_id: str, client_id: str, decision_engine_manager) -> Dict[str, Any]:
    """
    Get switch recommendation for agent

    Args:
        agent_id: Agent UUID
        client_id: Client ID for authorization
        decision_engine_manager: Decision engine manager instance

    Returns:
        Recommendation with auto-execute flag
    """
    # Get agent data
    agent = execute_query("""
        SELECT
            a.id,
            a.enabled,
            a.auto_switch_enabled,
            a.instance_id,
            a.instance_type,
            a.region,
            a.az,
            a.current_mode,
            a.current_pool_id,
            i.spot_price,
            i.ondemand_price,
            COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
            COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
            COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
            COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
        FROM agents a
        LEFT JOIN instances i ON a.instance_id = i.id
        LEFT JOIN agent_configs ac ON ac.agent_id = a.id
        WHERE a.id = %s AND a.client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not agent:
        raise ValueError('Agent not found')

    if not agent['enabled']:
        return {
            'recommended_action': 'stay',
            'reason': 'Agent is disabled',
            'will_auto_execute': False
        }

    # Get current pricing data
    latest_pricing = execute_query("""
        SELECT *
        FROM pricing_reports
        WHERE agent_id = %s
        ORDER BY collected_at DESC
        LIMIT 1
    """, (agent_id,), fetch_one=True)

    if not latest_pricing:
        return {
            'recommended_action': 'stay',
            'reason': 'No pricing data available',
            'will_auto_execute': False
        }

    # Prepare instance and pricing data for decision engine
    instance_data = {
        'instance_id': agent['instance_id'],
        'instance_type': agent['instance_type'],
        'region': agent['region'],
        'az': agent['az'],
        'current_mode': agent['current_mode'],
        'current_pool_id': agent['current_pool_id']
    }

    pricing_data = {
        'current_spot_price': latest_pricing['current_spot_price'],
        'on_demand_price': latest_pricing['on_demand_price'],
        'cheapest_pool': {
            'pool_id': latest_pricing['cheapest_pool_id'],
            'price': latest_pricing['cheapest_pool_price']
        },
        'spot_pools': json.loads(latest_pricing['spot_pools']) if latest_pricing['spot_pools'] else []
    }

    # Get recent switches
    recent_switches = execute_query("""
        SELECT COUNT(*) as count
        FROM switches
        WHERE agent_id = %s AND initiated_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """, (agent_id,), fetch_one=True)

    last_switch = execute_query("""
        SELECT initiated_at FROM switches
        WHERE agent_id = %s
        ORDER BY initiated_at DESC
        LIMIT 1
    """, (agent_id,), fetch_one=True)

    # Make decision
    decision = decision_engine_manager.make_decision(
        instance=instance_data,
        pricing=pricing_data,
        config_data=agent,
        recent_switches_count=recent_switches['count'] if recent_switches else 0,
        last_switch_time=last_switch['initiated_at'] if last_switch else None
    )

    # Add auto-execute flag
    decision['will_auto_execute'] = agent['auto_switch_enabled'] and decision.get('allowed', False)

    return decision


def get_replica_config(agent_id: str, client_id: str) -> Dict[str, Any]:
    """Get replica configuration for agent"""
    agent = execute_query("""
        SELECT
            replica_enabled,
            replica_count,
            manual_replica_enabled
        FROM agents
        WHERE id = %s AND client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not agent:
        raise ValueError('Agent not found')

    return {
        'replica_enabled': agent['replica_enabled'],
        'replica_count': agent['replica_count'],
        'manual_replica_enabled': agent.get('manual_replica_enabled', False)
    }
