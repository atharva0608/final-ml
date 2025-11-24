"""
AWS Spot Optimizer - Client API Routes
=======================================
API endpoints for client dashboard and management
"""

import logging
from flask import Blueprint, request, jsonify

from backend.auth import require_client_token
from backend.services import (
    client_service,
    instance_service,
    pricing_service
)

logger = logging.getLogger(__name__)

# Create Blueprint
client_bp = Blueprint('client', __name__, url_prefix='/api/client')


# ==============================================================================
# CLIENT INFORMATION
# ==============================================================================

@client_bp.route('/validate', methods=['GET'])
@require_client_token
def validate_token():
    """Validate client token"""
    return jsonify({'valid': True, 'client_id': request.client_id}), 200


@client_bp.route('/<client_id>', methods=['GET'])
@require_client_token
def get_client(client_id: str):
    """Get client information"""
    try:
        result = client_service.get_client_info(client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get client error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# AGENT MANAGEMENT
# ==============================================================================

@client_bp.route('/<client_id>/agents', methods=['GET'])
@require_client_token
def get_agents(client_id: str):
    """Get all agents for client"""
    try:
        result = client_service.get_client_agents(client_id)
        return jsonify({'agents': result}), 200
    except Exception as e:
        logger.error(f"Get agents error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/<client_id>/agents/decisions', methods=['GET'])
@require_client_token
def get_agent_decisions(client_id: str):
    """Get recent decisions for client's agents"""
    try:
        days = int(request.args.get('days', 7))
        result = client_service.get_agent_decisions(client_id, days)
        return jsonify({'decisions': result}), 200
    except Exception as e:
        logger.error(f"Get agent decisions error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/agents/<agent_id>/toggle-enabled', methods=['POST'])
@require_client_token
def toggle_agent_enabled(agent_id: str):
    """Toggle agent enabled status"""
    try:
        result = client_service.toggle_agent_enabled(agent_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Toggle agent enabled error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/agents/<agent_id>/settings', methods=['POST'])
@require_client_token
def update_agent_settings(agent_id: str):
    """Update agent settings"""
    try:
        result = client_service.update_agent_settings(agent_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Update agent settings error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/agents/<agent_id>/config', methods=['POST'])
@require_client_token
def update_agent_config(agent_id: str):
    """Update agent configuration"""
    try:
        result = client_service.update_agent_config(agent_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Update agent config error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/agents/<agent_id>', methods=['DELETE'])
@require_client_token
def delete_agent(agent_id: str):
    """Delete agent"""
    try:
        result = client_service.delete_agent(agent_id, request.client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Delete agent error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/<client_id>/agents/history', methods=['GET'])
@require_client_token
def get_agent_history(client_id: str):
    """Get agent activity history"""
    try:
        days = int(request.args.get('days', 30))
        result = client_service.get_agent_history(client_id, days)
        return jsonify({'history': result}), 200
    except Exception as e:
        logger.error(f"Get agent history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# INSTANCE MANAGEMENT
# ==============================================================================

@client_bp.route('/<client_id>/instances', methods=['GET'])
@require_client_token
def get_instances(client_id: str):
    """Get all instances for client"""
    try:
        result = instance_service.get_client_instances(client_id)
        return jsonify({'instances': result}), 200
    except Exception as e:
        logger.error(f"Get instances error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/instances/<instance_id>/pricing', methods=['GET'])
@require_client_token
def get_instance_pricing(instance_id: str):
    """Get pricing information for instance"""
    try:
        result = instance_service.get_instance_pricing(instance_id, request.client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get instance pricing error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/instances/<instance_id>/metrics', methods=['GET'])
@require_client_token
def get_instance_metrics(instance_id: str):
    """Get metrics for instance"""
    try:
        days = int(request.args.get('days', 7))
        result = instance_service.get_instance_metrics(instance_id, request.client_id, days)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get instance metrics error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/instances/<instance_id>/price-history', methods=['GET'])
@require_client_token
def get_price_history(instance_id: str):
    """Get price history for instance"""
    try:
        days = int(request.args.get('days', 7))
        result = instance_service.get_price_history(instance_id, request.client_id, days)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get price history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/pricing-history', methods=['GET'])
@require_client_token
def get_client_pricing_history():
    """Get pricing history for client (optionally filtered by agent_id)"""
    try:
        client_id = request.client_id
        days = int(request.args.get('days', 7))
        agent_id = request.args.get('agent_id')

        if agent_id:
            result = pricing_service.get_pricing_history(agent_id, days)
        else:
            # Get for all agents
            result = pricing_service.get_pricing_history(client_id, days)

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get pricing history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/instances/<instance_id>/available-options', methods=['GET'])
@require_client_token
def get_available_options(instance_id: str):
    """Get available switch options for instance"""
    try:
        result = instance_service.get_available_options(instance_id, request.client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get available options error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/instances/<instance_id>/force-switch', methods=['POST'])
@require_client_token
def force_switch(instance_id: str):
    """Force instance switch"""
    try:
        from backend.services import switch_service
        result = switch_service.force_switch(instance_id, request.client_id, request.json or {})
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Force switch error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# REPLICA MANAGEMENT
# ==============================================================================

@client_bp.route('/<client_id>/replicas', methods=['GET'])
@require_client_token
def get_replicas(client_id: str):
    """Get all replicas for client"""
    try:
        result = client_service.get_client_replicas(client_id)
        return jsonify({'replicas': result}), 200
    except Exception as e:
        logger.error(f"Get replicas error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# SAVINGS AND STATISTICS
# ==============================================================================

@client_bp.route('/<client_id>/savings', methods=['GET'])
@require_client_token
def get_savings(client_id: str):
    """Get savings statistics for client"""
    try:
        days = int(request.args.get('days', 30))
        result = client_service.get_client_savings(client_id, days)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get savings error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/<client_id>/switch-history', methods=['GET'])
@require_client_token
def get_switch_history(client_id: str):
    """Get switch history for client"""
    try:
        days = int(request.args.get('days', 30))
        result = client_service.get_switch_history(client_id, days)
        return jsonify({'history': result}), 200
    except Exception as e:
        logger.error(f"Get switch history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/<client_id>/stats/charts', methods=['GET'])
@require_client_token
def get_chart_stats(client_id: str):
    """Get chart statistics for client"""
    try:
        days = int(request.args.get('days', 30))
        result = client_service.get_chart_stats(client_id, days)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get chart stats error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# EXPORTS
# ==============================================================================

@client_bp.route('/<client_id>/export/savings', methods=['GET'])
@require_client_token
def export_savings(client_id: str):
    """Export client savings as CSV"""
    try:
        result = client_service.export_client_savings(client_id)
        return result
    except Exception as e:
        logger.error(f"Export savings error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@client_bp.route('/<client_id>/export/history', methods=['GET'])
@require_client_token
def export_history(client_id: str):
    """Export switch history as CSV"""
    try:
        result = client_service.export_switch_history(client_id)
        return result
    except Exception as e:
        logger.error(f"Export history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
