"""
AWS Spot Optimizer - Agent Service
===================================
Business logic for agent operations
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from marshmallow import ValidationError

from backend.database_manager import execute_query
from backend.utils import generate_uuid, log_system_event, create_notification
from backend.schemas import AgentRegistrationSchema, HeartbeatSchema

logger = logging.getLogger(__name__)


def register_agent(client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Register or update an agent

    Args:
        client_id: Client ID for authorization
        data: Agent registration data

    Returns:
        Agent ID and configuration
    """
    logger.info(f"Agent registration attempt from client {client_id}")
    logger.debug(f"Registration data: {data}")

    # Validate input
    schema = AgentRegistrationSchema()
    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        logger.warning(f"Agent registration validation failed: {e.messages}")
        log_system_event('validation_error', 'warning',
                        f"Agent registration validation failed: {e.messages}",
                        client_id)
        raise ValueError(f"Validation failed: {e.messages}")

    logical_agent_id = validated_data['logical_agent_id']
    logger.info(f"Agent registration validated: logical_id={logical_agent_id}, instance_id={validated_data['instance_id']}, mode={validated_data['mode']}")

    # Check if agent exists
    existing = execute_query(
        "SELECT id FROM agents WHERE logical_agent_id = %s AND client_id = %s",
        (logical_agent_id, client_id),
        fetch_one=True
    )

    if existing:
        agent_id = existing['id']
        logger.info(f"Updating existing agent: agent_id={agent_id}, logical_id={logical_agent_id}")
        # Update existing agent
        execute_query("""
            UPDATE agents
            SET status = 'online',
                hostname = %s,
                instance_id = %s,
                instance_type = %s,
                region = %s,
                az = %s,
                ami_id = %s,
                current_mode = %s,
                current_pool_id = %s,
                agent_version = %s,
                private_ip = %s,
                public_ip = %s,
                last_heartbeat_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """, (
            validated_data.get('hostname'),
            validated_data['instance_id'],
            validated_data['instance_type'],
            validated_data['region'],
            validated_data['az'],
            validated_data.get('ami_id'),
            validated_data['mode'],
            f"{validated_data['instance_type']}.{validated_data['az']}" if validated_data['mode'] == 'spot' else None,
            validated_data.get('agent_version'),
            validated_data.get('private_ip'),
            validated_data.get('public_ip'),
            agent_id
        ))
    else:
        # Insert new agent
        agent_id = generate_uuid()
        logger.info(f"Creating new agent: agent_id={agent_id}, logical_id={logical_agent_id}")
        execute_query("""
            INSERT INTO agents
            (id, client_id, logical_agent_id, hostname, instance_id, instance_type,
             region, az, ami_id, current_mode, current_pool_id, agent_version,
             private_ip, public_ip, status, last_heartbeat_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'online', NOW())
        """, (
            agent_id,
            client_id,
            logical_agent_id,
            validated_data.get('hostname'),
            validated_data['instance_id'],
            validated_data['instance_type'],
            validated_data['region'],
            validated_data['az'],
            validated_data.get('ami_id'),
            validated_data['mode'],
            f"{validated_data['instance_type']}.{validated_data['az']}" if validated_data['mode'] == 'spot' else None,
            validated_data.get('agent_version'),
            validated_data.get('private_ip'),
            validated_data.get('public_ip')
        ))

        # Create default config
        execute_query("""
            INSERT INTO agent_configs (agent_id)
            VALUES (%s)
        """, (agent_id,))

        create_notification(
            f"New agent registered: {logical_agent_id}",
            'info',
            client_id
        )

    # Handle instance registration
    instance_exists = execute_query(
        "SELECT id FROM instances WHERE id = %s",
        (validated_data['instance_id'],),
        fetch_one=True
    )

    if not instance_exists:
        # Get latest on-demand price
        latest_od_price = execute_query("""
            SELECT price FROM ondemand_prices
            WHERE region = %s AND instance_type = %s
            LIMIT 1
        """, (validated_data['region'], validated_data['instance_type']), fetch_one=True)

        if not latest_od_price:
            # Fallback to snapshots
            latest_od_price = execute_query("""
                SELECT price FROM ondemand_price_snapshots
                WHERE region = %s AND instance_type = %s
                ORDER BY captured_at DESC
                LIMIT 1
            """, (validated_data['region'], validated_data['instance_type']), fetch_one=True)

        baseline_price = latest_od_price['price'] if latest_od_price else 0.0416

        # Get spot price if in spot mode
        spot_price = 0
        if validated_data['mode'] == 'spot':
            pool_id = validated_data.get('pool_id', f"{validated_data['instance_type']}.{validated_data['az']}")
            latest_spot = execute_query("""
                SELECT price FROM spot_price_snapshots
                WHERE pool_id = %s
                ORDER BY captured_at DESC
                LIMIT 1
            """, (pool_id,), fetch_one=True)
            spot_price = latest_spot['price'] if latest_spot else baseline_price * 0.3

        execute_query("""
            INSERT INTO instances
            (id, client_id, agent_id, instance_type, region, az, ami_id,
             current_mode, current_pool_id, spot_price, ondemand_price, baseline_ondemand_price,
             is_active, installed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
        """, (
            validated_data['instance_id'],
            client_id,
            agent_id,
            validated_data['instance_type'],
            validated_data['region'],
            validated_data['az'],
            validated_data.get('ami_id'),
            validated_data['mode'],
            validated_data.get('pool_id') if validated_data['mode'] == 'spot' else None,
            spot_price if validated_data['mode'] == 'spot' else 0,
            baseline_price,
            baseline_price
        ))

    # Get agent config
    config_data = execute_query("""
        SELECT
            a.enabled,
            a.auto_switch_enabled,
            a.auto_terminate_enabled,
            a.terminate_wait_seconds,
            a.replica_enabled,
            a.replica_count,
            COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
            COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
            COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
            COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
        FROM agents a
        LEFT JOIN agent_configs ac ON ac.agent_id = a.id
        WHERE a.id = %s
    """, (agent_id,), fetch_one=True)

    log_system_event('agent_registered', 'info',
                    f"Agent {logical_agent_id} registered successfully",
                    client_id, agent_id, validated_data['instance_id'])

    logger.info(f"✓ Agent registered successfully: agent_id={agent_id}, logical_id={logical_agent_id}")

    return {
        'agent_id': agent_id,
        'client_id': client_id,
        'config': {
            'enabled': config_data['enabled'],
            'auto_switch_enabled': config_data['auto_switch_enabled'],
            'auto_terminate_enabled': config_data['auto_terminate_enabled'],
            'terminate_wait_seconds': config_data['terminate_wait_seconds'],
            'replica_enabled': config_data['replica_enabled'],
            'replica_count': config_data['replica_count'],
            'min_savings_percent': float(config_data['min_savings_percent']),
            'risk_threshold': float(config_data['risk_threshold']),
            'max_switches_per_week': config_data['max_switches_per_week'],
            'min_pool_duration_hours': config_data['min_pool_duration_hours']
        }
    }


def update_heartbeat(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update agent heartbeat

    Args:
        agent_id: Agent UUID
        client_id: Client ID for authorization
        data: Heartbeat data

    Returns:
        Success response
    """
    new_status = data.get('status', 'online')

    # Get previous status
    prev = execute_query(
        "SELECT status FROM agents WHERE id = %s AND client_id = %s",
        (agent_id, client_id),
        fetch_one=True
    )

    if not prev:
        raise ValueError('Agent not found')

    # Update heartbeat
    execute_query("""
        UPDATE agents
        SET status = %s,
            last_heartbeat_at = NOW(),
            instance_id = COALESCE(%s, instance_id),
            instance_type = COALESCE(%s, instance_type),
            current_mode = COALESCE(%s, current_mode),
            az = COALESCE(%s, az)
        WHERE id = %s AND client_id = %s
    """, (
        new_status,
        data.get('instance_id'),
        data.get('instance_type'),
        data.get('mode'),
        data.get('az'),
        agent_id,
        client_id
    ))

    # Log status changes
    if prev['status'] != new_status:
        logger.info(f"Agent {agent_id} status changed: {prev['status']} → {new_status}")
        log_system_event('agent_status_change', 'info',
                        f"Agent status changed from {prev['status']} to {new_status}",
                        client_id, agent_id)

    return {'success': True}


def get_agent_config(agent_id: str, client_id: str) -> Dict[str, Any]:
    """Get agent configuration"""
    config = execute_query("""
        SELECT
            a.enabled,
            a.auto_switch_enabled,
            a.auto_terminate_enabled,
            a.terminate_wait_seconds,
            a.replica_enabled,
            a.replica_count,
            COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
            COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
            COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
            COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
        FROM agents a
        LEFT JOIN agent_configs ac ON ac.agent_id = a.id
        WHERE a.id = %s AND a.client_id = %s
    """, (agent_id, client_id), fetch_one=True)

    if not config:
        raise ValueError('Agent not found')

    return {
        'enabled': config['enabled'],
        'auto_switch_enabled': config['auto_switch_enabled'],
        'auto_terminate_enabled': config['auto_terminate_enabled'],
        'terminate_wait_seconds': config['terminate_wait_seconds'],
        'replica_enabled': config['replica_enabled'],
        'replica_count': config['replica_count'],
        'min_savings_percent': float(config['min_savings_percent']),
        'risk_threshold': float(config['risk_threshold']),
        'max_switches_per_week': config['max_switches_per_week'],
        'min_pool_duration_hours': config['min_pool_duration_hours']
    }


def get_pending_commands(agent_id: str, client_id: str) -> Dict[str, Any]:
    """Get pending commands for agent"""
    commands = execute_query("""
        SELECT id, command_type, params, created_at
        FROM commands
        WHERE agent_id = %s AND status = 'pending'
        ORDER BY created_at ASC
    """, (agent_id,), fetch=True)

    return {'commands': commands or []}


def mark_command_executed(agent_id: str, command_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Mark command as executed"""
    execute_query("""
        UPDATE commands
        SET status = 'executed',
            executed_at = NOW(),
            result = %s
        WHERE id = %s AND agent_id = %s
    """, (json.dumps(data.get('result', {})), command_id, agent_id))

    return {'success': True}


def record_termination(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Record instance termination"""
    instance_id = data.get('instance_id')
    reason = data.get('reason', 'unknown')

    # Mark agent as offline
    execute_query("""
        UPDATE agents
        SET status = 'offline'
        WHERE id = %s AND client_id = %s
    """, (agent_id, client_id))

    # Mark instance as inactive
    execute_query("""
        UPDATE instances
        SET is_active = FALSE, terminated_at = NOW()
        WHERE id = %s AND client_id = %s
    """, (instance_id, client_id))

    log_system_event('instance_terminated', 'warning',
                    f"Instance {instance_id} terminated: {reason}",
                    client_id, agent_id, instance_id)

    logger.info(f"Instance {instance_id} terminated: {reason}")

    return {'success': True}


def record_cleanup(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Record post-switch cleanup"""
    old_instance_id = data.get('old_instance_id')
    cleanup_success = data.get('success', False)
    cleanup_time = data.get('cleanup_time_seconds', 0)

    execute_query("""
        UPDATE instances
        SET is_active = FALSE, terminated_at = NOW()
        WHERE id = %s AND client_id = %s
    """, (old_instance_id, client_id))

    logger.info(f"Cleanup complete for {old_instance_id}: success={cleanup_success}, time={cleanup_time}s")

    return {'success': True}


def handle_rebalance_recommendation(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle AWS rebalance recommendation"""
    instance_id = data.get('instance_id')
    notice_time = data.get('notice_time')

    logger.warning(f"Rebalance recommendation received for agent {agent_id}, instance {instance_id}")

    log_system_event('rebalance_recommendation', 'warning',
                    f"AWS rebalance recommendation received for instance {instance_id}",
                    client_id, agent_id, instance_id)

    # Check if replica already exists
    existing_replica = execute_query("""
        SELECT id FROM replica_instances
        WHERE agent_id = %s AND status IN ('launching', 'syncing', 'ready')
    """, (agent_id,), fetch_one=True)

    if existing_replica:
        return {
            'action': 'none',
            'message': 'Replica already exists',
            'replica_id': existing_replica['id']
        }

    # Create emergency replica (will be handled by replica_service)
    return {
        'action': 'create_replica',
        'message': 'Emergency replica creation recommended'
    }
