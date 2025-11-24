"""
AWS Spot Optimizer - Agent API Routes
======================================
API endpoints for agent communication

All Priority 1 (Agent Core) endpoints - CRITICAL for agent operations
"""

import logging
from flask import Blueprint, request, jsonify

from backend.auth import require_client_token
from backend.services import (
    agent_service,
    pricing_service,
    switch_service,
    decision_service
)

logger = logging.getLogger(__name__)

# Create Blueprint
agent_bp = Blueprint('agent', __name__, url_prefix='/api/agents')


# ==============================================================================
# AGENT LIFECYCLE - Registration and Heartbeat
# ==============================================================================

@agent_bp.route('/register', methods=['POST'])
@require_client_token
def register():
    """Register new agent"""
    try:
        result = agent_service.register_agent(request.client_id, request.json)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Agent registration error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/heartbeat', methods=['POST'])
@require_client_token
def heartbeat(agent_id: str):
    """Update agent heartbeat"""
    try:
        result = agent_service.update_heartbeat(agent_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Heartbeat error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/config', methods=['GET'])
@require_client_token
def get_config(agent_id: str):
    """Get agent configuration"""
    try:
        result = agent_service.get_agent_config(agent_id, request.client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get config error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# COMMAND MANAGEMENT
# ==============================================================================

@agent_bp.route('/<agent_id>/pending-commands', methods=['GET'])
@require_client_token
def get_pending_commands(agent_id: str):
    """Get pending commands for agent"""
    try:
        result = agent_service.get_pending_commands(agent_id, request.client_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get pending commands error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/commands/<command_id>/executed', methods=['POST'])
@require_client_token
def mark_command_executed(agent_id: str, command_id: str):
    """Mark command as executed"""
    try:
        result = agent_service.mark_command_executed(agent_id, command_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Mark command executed error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# PRICING AND MONITORING
# ==============================================================================

@agent_bp.route('/<agent_id>/pricing-report', methods=['POST'])
@require_client_token
def pricing_report(agent_id: str):
    """
    Receive pricing data from agent

    Agent sends pricing snapshots every 5 minutes containing:
    - Current instance pricing (spot & on-demand)
    - All available spot pools with prices
    - Cheapest pool identification
    """
    try:
        result = pricing_service.store_pricing_report(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Pricing report error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# SWITCHING AND FAILOVER
# ==============================================================================

@agent_bp.route('/<agent_id>/switch-report', methods=['POST'])
@require_client_token
def switch_report(agent_id: str):
    """Record instance switch event"""
    try:
        result = switch_service.record_switch(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Switch report error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/termination', methods=['POST'])
@require_client_token
def termination_report(agent_id: str):
    """Handle instance termination"""
    try:
        result = agent_service.record_termination(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Termination report error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/cleanup-report', methods=['POST'])
@require_client_token
def cleanup_report(agent_id: str):
    """Report cleanup after switch"""
    try:
        result = agent_service.record_cleanup(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Cleanup report error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# SPOT INTERRUPTION DEFENSE
# ==============================================================================

@agent_bp.route('/<agent_id>/rebalance-recommendation', methods=['POST'])
@require_client_token
def rebalance_recommendation(agent_id: str):
    """Handle AWS rebalance recommendation"""
    try:
        result = agent_service.handle_rebalance_recommendation(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Rebalance recommendation error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# REPLICA CONFIGURATION
# ==============================================================================

@agent_bp.route('/<agent_id>/replica-config', methods=['GET'])
@require_client_token
def get_replica_config(agent_id: str):
    """Get replica configuration"""
    try:
        result = decision_service.get_replica_config(agent_id, request.client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get replica config error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# ML DECISION ENGINE
# ==============================================================================

@agent_bp.route('/<agent_id>/decide', methods=['POST'])
@require_client_token
def decide(agent_id: str):
    """Request switching decision from ML model"""
    try:
        # Import decision engine manager
        from backend.decision_engine_manager import decision_engine_manager
        result = decision_service.make_decision(agent_id, request.client_id, request.json, decision_engine_manager)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Decision error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/switch-recommendation', methods=['GET'])
@require_client_token
def switch_recommendation(agent_id: str):
    """Get switch recommendation"""
    try:
        from backend.decision_engine_manager import decision_engine_manager
        result = decision_service.get_switch_recommendation(agent_id, request.client_id, decision_engine_manager)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Switch recommendation error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/<agent_id>/issue-switch-command', methods=['POST'])
@require_client_token
def issue_switch_command(agent_id: str):
    """Issue switch command to agent"""
    try:
        result = switch_service.issue_switch_command(agent_id, request.client_id, request.json)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f"Issue switch command error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
