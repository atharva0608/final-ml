"""
AWS Spot Optimizer - Switch Service
====================================
Business logic for instance switching operations
"""

import json
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from backend.database_manager import execute_query
from backend.utils import generate_uuid, log_system_event, create_notification

logger = logging.getLogger(__name__)


def record_switch(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Record instance switch event

    Args:
        agent_id: Agent UUID
        client_id: Client ID for authorization
        data: Switch report data

    Returns:
        Success response
    """
    old_inst = data.get('old_instance', {})
    new_inst = data.get('new_instance', {})
    timing = data.get('timing', {})
    prices = data.get('pricing', {})

    # Get agent's auto_terminate setting
    agent = execute_query("""
        SELECT auto_terminate_enabled FROM agents WHERE id = %s
    """, (agent_id,), fetch_one=True)

    auto_terminate_enabled = agent.get('auto_terminate_enabled', True) if agent else True

    # Calculate savings impact
    old_price = prices.get('old_spot') or prices.get('on_demand', 0)
    new_price = prices.get('new_spot') or prices.get('on_demand', 0)
    savings_impact = old_price - new_price

    # Insert switch record
    switch_id = generate_uuid()
    execute_query("""
        INSERT INTO switches (
            id, client_id, agent_id, command_id,
            old_instance_id, old_instance_type, old_region, old_az, old_mode, old_pool_id, old_ami_id,
            new_instance_id, new_instance_type, new_region, new_az, new_mode, new_pool_id, new_ami_id,
            on_demand_price, old_spot_price, new_spot_price, savings_impact,
            event_trigger, trigger_type, timing_data,
            initiated_at, ami_created_at, instance_launched_at, instance_ready_at, old_terminated_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """, (
        switch_id, client_id, agent_id, data.get('command_id'),
        old_inst.get('instance_id'), old_inst.get('instance_type'), old_inst.get('region'),
        old_inst.get('az'), old_inst.get('mode'), old_inst.get('pool_id'), old_inst.get('ami_id'),
        new_inst.get('instance_id'), new_inst.get('instance_type'), new_inst.get('region'),
        new_inst.get('az'), new_inst.get('mode'), new_inst.get('pool_id'), new_inst.get('ami_id'),
        prices.get('on_demand'), prices.get('old_spot'), prices.get('new_spot'), savings_impact,
        data.get('trigger'), data.get('trigger'), json.dumps(timing),
        timing.get('initiated_at'), timing.get('ami_created_at'),
        timing.get('instance_launched_at'), timing.get('instance_ready_at'),
        timing.get('old_terminated_at')
    ))

    # Mark old instance as terminated if auto_terminate is enabled
    if auto_terminate_enabled and timing.get('old_terminated_at'):
        execute_query("""
            UPDATE instances
            SET is_active = FALSE, terminated_at = %s
            WHERE id = %s AND client_id = %s
        """, (timing.get('old_terminated_at'), old_inst.get('instance_id'), client_id))
        logger.info(f"Old instance {old_inst.get('instance_id')} marked as terminated (auto_terminate=ON)")
    else:
        logger.info(f"Old instance {old_inst.get('instance_id')} kept active (auto_terminate=OFF)")

    # Register new instance
    execute_query("""
        INSERT INTO instances (
            id, client_id, agent_id, instance_type, region, az, ami_id,
            current_mode, current_pool_id, spot_price, ondemand_price,
            is_active, installed_at, last_switch_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
        ON DUPLICATE KEY UPDATE
            current_mode = VALUES(current_mode),
            current_pool_id = VALUES(current_pool_id),
            spot_price = VALUES(spot_price),
            is_active = TRUE,
            last_switch_at = VALUES(last_switch_at)
    """, (
        new_inst.get('instance_id'), client_id, agent_id,
        new_inst.get('instance_type'), new_inst.get('region'), new_inst.get('az'),
        new_inst.get('ami_id'), new_inst.get('mode'), new_inst.get('pool_id'),
        prices.get('new_spot', 0), prices.get('on_demand'),
        timing.get('instance_launched_at'), timing.get('instance_launched_at')
    ))

    # Update agent with new instance info
    execute_query("""
        UPDATE agents
        SET instance_id = %s,
            current_mode = %s,
            current_pool_id = %s,
            last_switch_at = NOW()
        WHERE id = %s
    """, (
        new_inst.get('instance_id'),
        new_inst.get('mode'),
        new_inst.get('pool_id'),
        agent_id
    ))

    # Update total savings
    if savings_impact > 0:
        execute_query("""
            UPDATE clients
            SET total_savings = total_savings + %s
            WHERE id = %s
        """, (savings_impact * 24, client_id))

    create_notification(
        f"Instance switched: {new_inst.get('instance_id')} - Saved ${savings_impact:.4f}/hr",
        'info',
        client_id
    )

    log_system_event('switch_completed', 'info',
                    f"Switch from {old_inst.get('instance_id')} to {new_inst.get('instance_id')}",
                    client_id, agent_id, new_inst.get('instance_id'),
                    metadata={'savings_impact': float(savings_impact)})

    return {'success': True}


def issue_switch_command(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Issue switch command to agent"""
    # Check if auto_switch is enabled
    agent = execute_query("""
        SELECT auto_switch_enabled FROM agents
        WHERE id = %s AND client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not agent:
        raise ValueError('Agent not found')

    if not agent.get('auto_switch_enabled', False):
        raise ValueError('Auto-switch is disabled for this agent')

    # Create switch command
    command_id = generate_uuid()
    execute_query("""
        INSERT INTO commands (id, agent_id, command_type, params, status)
        VALUES (%s, %s, 'switch', %s, 'pending')
    """, (command_id, agent_id, json.dumps(data)))

    logger.info(f"Switch command issued: agent={agent_id}, command={command_id}")

    return {
        'command_id': command_id,
        'status': 'pending'
    }


def get_switch_history(client_id: str, days: int = 30) -> Dict[str, Any]:
    """Get switch history for client"""
    history = execute_query("""
        SELECT
            s.id,
            s.agent_id,
            s.old_instance_id,
            s.new_instance_id,
            s.old_mode,
            s.new_mode,
            s.savings_impact,
            s.event_trigger,
            s.initiated_at,
            s.instance_ready_at,
            a.logical_agent_id
        FROM switches s
        JOIN agents a ON s.agent_id = a.id
        WHERE s.client_id = %s
          AND s.initiated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY s.initiated_at DESC
    """, (client_id, days), fetch=True)

    total_savings = sum(s.get('savings_impact', 0) for s in (history or []))

    return {
        'history': history or [],
        'total_switches': len(history or []),
        'total_savings': float(total_savings),
        'days': days
    }


def force_switch(instance_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Force instance switch"""
    target = data.get('target')
    pool_id = data.get('pool_id')
    new_instance_type = data.get('new_instance_type')

    # Get instance and agent info
    instance = execute_query("""
        SELECT i.*, a.id as agent_id, a.logical_agent_id
        FROM instances i
        JOIN agents a ON i.agent_id = a.id
        WHERE i.id = %s AND i.client_id = %s
    """, (instance_id, client_id), fetch_one=True)

    if not instance:
        raise ValueError('Instance not found')

    agent_id = instance['agent_id']

    # Create force-switch command
    command_params = {
        'target': target,
        'pool_id': pool_id,
        'new_instance_type': new_instance_type,
        'force': True
    }

    command_id = generate_uuid()
    execute_query("""
        INSERT INTO commands (id, agent_id, command_type, params, status)
        VALUES (%s, %s, 'force-switch', %s, 'pending')
    """, (command_id, agent_id, json.dumps(command_params)))

    logger.info(f"Force switch command issued: instance={instance_id}, target={target}, command={command_id}")

    create_notification(
        f"Force switch initiated for {instance['logical_agent_id']} to {target}",
        'info',
        client_id
    )

    return {
        'command_id': command_id,
        'status': 'pending',
        'message': f'Force switch to {target} initiated'
    }
