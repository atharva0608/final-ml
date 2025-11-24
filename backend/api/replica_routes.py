"""
Flask Blueprint for Replica Management Endpoints

This module contains all replica-related API routes for:
- Manual replica management (create, list, promote, delete, update, status)
- Emergency replica management (spot interruption defense)
- Replica sync status updates

All routes are protected with @require_client_token decorator.
"""

import logging
from flask import Blueprint, request, jsonify

from backend.auth import require_client_token
from backend.database_manager import execute_query
from backend.services import replica_service

logger = logging.getLogger(__name__)

# Create blueprint with /api/agents prefix
replica_bp = Blueprint('replica', __name__, url_prefix='/api/agents')


# ============================================================================
# MANUAL REPLICA MANAGEMENT ROUTES
# ============================================================================

@replica_bp.route('/<agent_id>/replicas', methods=['POST'])
@require_client_token
def create_replica(agent_id):
    """
    Create a manual replica for an agent instance.

    Request body:
        - pool_id (optional): Target pool ID (auto-selected if not provided)
        - exclude_zones (optional): List of zones to exclude
        - max_hourly_cost (optional): Maximum hourly cost limit
        - tags (optional): Custom tags for the replica
        - created_by (optional): Creator identifier

    Returns:
        201: Replica created successfully
        400: Invalid request or replica limit reached
        404: Agent not found
        500: Server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.create_manual_replica_logic(
            execute_query,
            agent_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in create_replica endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas', methods=['GET'])
@require_client_token
def list_replicas(agent_id):
    """
    List all replicas for an agent.

    Query parameters:
        - include_terminated (optional): Include terminated replicas (default: false)

    Returns:
        200: List of replicas
        500: Server error
    """
    try:
        include_terminated = request.args.get('include_terminated', 'false').lower() == 'true'
        result = replica_service.list_replicas_logic(
            execute_query,
            agent_id,
            include_terminated
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in list_replicas endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas/<replica_id>/promote', methods=['POST'])
@require_client_token
def promote_replica(agent_id, replica_id):
    """
    Promote replica to primary (manual failover).

    Request body:
        - demote_old_primary (optional): Whether to demote old primary to replica (default: true)
        - wait_for_sync (optional): Wait for sync before promoting (default: true)

    Returns:
        200: Replica promoted successfully
        400: Replica not ready for promotion
        404: Replica or agent not found
        500: Server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.promote_replica_logic(
            execute_query,
            agent_id,
            replica_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in promote_replica endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas/<replica_id>', methods=['DELETE'])
@require_client_token
def delete_replica(agent_id, replica_id):
    """
    Gracefully terminate a replica.

    Returns:
        200: Replica terminated successfully
        400: Replica already terminated
        404: Replica not found
        500: Server error
    """
    try:
        result = replica_service.delete_replica_logic(
            execute_query,
            agent_id,
            replica_id
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in delete_replica endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas/<replica_id>', methods=['PUT'])
@require_client_token
def update_replica(agent_id, replica_id):
    """
    Update replica with actual EC2 instance ID after launch.
    Called by agent after launching EC2 instance.

    Request body:
        - instance_id (required): Actual EC2 instance ID
        - status (optional): New status (default: 'syncing')

    Returns:
        200: Replica updated successfully
        400: Missing instance_id
        404: Replica not found
        500: Server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.update_replica_instance_logic(
            execute_query,
            agent_id,
            replica_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in update_replica endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas/<replica_id>/status', methods=['POST'])
@require_client_token
def update_status(agent_id, replica_id):
    """
    Update replica status and metadata.
    Called by agent during replica lifecycle.

    Request body:
        - status (required): New status (launching, syncing, ready, failed, terminated)
        - sync_started_at (optional): Sync start timestamp
        - sync_completed_at (optional): Sync completion timestamp
        - error_message (optional): Error message if status is 'failed'

    Returns:
        200: Status updated successfully
        400: Invalid status or missing required fields
        404: Replica not found
        500: Server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.update_replica_status_logic(
            execute_query,
            agent_id,
            replica_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in update_status endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/replicas/<replica_id>/sync-status', methods=['POST'])
@require_client_token
def update_sync_status(agent_id, replica_id):
    """
    Update replica sync status.
    Called by agent to report sync progress.

    Request body:
        - sync_status (optional): Sync status string
        - sync_latency_ms (optional): Current sync latency in milliseconds
        - state_transfer_progress (optional): Progress percentage (0-100)
        - status (optional): Overall replica status

    Returns:
        200: Sync status updated successfully
        400: No updates provided
        500: Server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.update_replica_sync_status_logic(
            execute_query,
            agent_id,
            replica_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in update_sync_status endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# EMERGENCY REPLICA MANAGEMENT ROUTES (SPOT INTERRUPTION DEFENSE)
# ============================================================================

@replica_bp.route('/<agent_id>/create-emergency-replica', methods=['POST'])
@require_client_token
def create_emergency(agent_id):
    """
    Create emergency replica in response to spot interruption signal.

    Request body:
        - signal_type (required): 'rebalance-recommendation' or 'termination-notice'
        - termination_time (optional): Expected termination timestamp
        - instance_id (optional): Current instance ID being interrupted
        - pool_id (optional): Current pool ID
        - preferred_zones (optional): List of preferred zones
        - exclude_zones (optional): List of zones to exclude

    Returns:
        201: Emergency replica created successfully
        400: Invalid signal_type
        403: Emergency replicas disabled (auto_switch_enabled is OFF)
        404: Agent not found
        500: No suitable pool found or server error
    """
    try:
        data = request.get_json() or {}
        result = replica_service.create_emergency_replica_logic(
            execute_query,
            agent_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in create_emergency endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@replica_bp.route('/<agent_id>/termination-imminent', methods=['POST'])
@require_client_token
def termination_imminent(agent_id):
    """
    Handle imminent termination (2-minute warning).
    Immediately promotes replica if available.

    Request body:
        - instance_id (optional): Instance being terminated
        - termination_time (optional): Expected termination timestamp
        - replica_id (optional): Specific replica to promote (auto-selected if not provided)

    Returns:
        200: Automatic failover completed successfully
        500: No replica available or failover failed
    """
    try:
        data = request.get_json() or {}
        result = replica_service.handle_termination_imminent_logic(
            execute_query,
            agent_id,
            data
        )

        if result['success']:
            return jsonify(result['data']), result['status_code']
        else:
            return jsonify({'error': result['error']}), result['status_code']

    except Exception as e:
        logger.error(f"Error in termination_imminent endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
